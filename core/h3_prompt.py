"""H3 prompt templates and deterministic validation."""

from __future__ import annotations

import re
from collections.abc import Mapping

from .contracts import normalize_mode
from .materials import compile_mentions

BASE_FIELDS = ("integrated_multimodal_description:", "overall_soundscape:", "non_diegetic_music:")
REF_FIELDS = (
    "subject_definitions:",
    "summary:",
    "retention_analysis:",
    "detailed_description:",
    "overall_soundscape:",
    "non_diegetic_music:",
)

KEYFRAME_TOKENS = {
    "I2VA": frozenset({"<Picture 1>"}),
    "FL2VA": frozenset({"<Picture 1>", "<Picture 2>"}),
    "L2VA": frozenset({"<Picture 1>"}),
}

KEYFRAME_ALIASES = {
    "I2VA": {
        "@首帧": "<Picture 1>",
        "@第一帧": "<Picture 1>",
        "@上一段尾帧": "<Picture 1>",
    },
    "FL2VA": {
        "@首帧": "<Picture 1>",
        "@第一帧": "<Picture 1>",
        "@尾帧": "<Picture 2>",
        "@最后一帧": "<Picture 2>",
    },
    "L2VA": {
        "@尾帧": "<Picture 1>",
        "@最后一帧": "<Picture 1>",
    },
}


def normalize_prompt_layout(text: str, mode: str) -> str:
    """Normalize H3 field blocks to the official one-field-per-section layout."""

    mode = normalize_mode(mode)
    value = str(text or "").replace("\\n", "\n").strip()
    fields = REF_FIELDS if mode == "Ref2VA" else BASE_FIELDS
    for field in fields:
        value = re.sub(rf"\s*{re.escape(field)}\s*", f"\n\n{field}\n", value, flags=re.IGNORECASE)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def instruction_for(mode: str, duration: float) -> str:
    mode = normalize_mode(mode)
    if mode == "I2VA":
        return "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."
    if mode == "FL2VA":
        return "How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the %.2f-second mark of the target video." % duration
    if mode == "L2VA":
        return "How the reference pictures align with the target video — <Picture 1> (from [Shot 1]) aligns with the %.2f-second mark of the target video." % duration
    return ""


def compile_draft(draft: str, mode: str, registry: Mapping | None, duration: float) -> tuple[str, tuple[str, ...]]:
    mode = normalize_mode(mode)
    # Keyframe modes do not consume the Ref2VA material pack. Their picture
    # labels are native input slots, so keep them independent from the
    # connected material registry and allow drafts to reserve them early.
    mention_registry = registry if mode == "Ref2VA" else None
    compiled, used = compile_mentions(
        draft,
        mention_registry,
        KEYFRAME_TOKENS.get(mode),
        KEYFRAME_ALIASES.get(mode),
    )
    compiled = normalize_prompt_layout(compiled, mode)
    # The image is already supplied through the native H3 input for I2VA,
    # FL2VA, and L2VA. Mentioning <Picture N> is useful but not mandatory;
    # H3 also accepts a natural-language prompt without a reference tag.
    instruction = instruction_for(mode, duration)
    return ((instruction + "\n\n" if instruction else "") + compiled.strip(), used)


def validate_prompt(
    text: str,
    mode: str,
    duration: float,
    registry: Mapping | None = None,
    *,
    strict_fields: bool = False,
) -> list[str]:
    """Validate prompt input. H3 accepts natural language, so the Context-IR
    field layout and [Shot N] timeline are only enforced when strict_fields is
    set; enabled-material references are always validated."""

    mode = normalize_mode(mode)
    value = str(text or "").strip()
    errors: list[str] = []
    if strict_fields:
        fields = REF_FIELDS if mode == "Ref2VA" else BASE_FIELDS
        positions = [value.find(field) for field in fields]
        if any(pos < 0 for pos in positions):
            missing = [field[:-1] for field, pos in zip(fields, positions) if pos < 0]
            errors.append("缺少字段：" + "、".join(missing))
        elif positions != sorted(positions):
            errors.append("H3 字段顺序不正确")
        for match in re.finditer(r"\[Shot\s+(\d+)\].*?(?:At\s+(\d+):(\d+\.\d+))?", value, re.IGNORECASE | re.DOTALL):
            if match.group(2):
                timestamp = int(match.group(2)) * 60 + float(match.group(3))
                if timestamp >= duration + 0.01:
                    errors.append(f"镜头时间 {timestamp:.3f}s 超过有效时长 {duration:.3f}s")
    if registry:
        valid_tokens = (
            set((registry.get("token_to_alias") or {}).keys())
            if mode == "Ref2VA"
            else set(KEYFRAME_TOKENS.get(mode, ()))
        )
        for token in re.findall(r"<(?:Picture|Video|Audio)\s+\d+>", value, re.IGNORECASE):
            canonical = re.sub(r"\s+", " ", token.title())
            if canonical not in valid_tokens:
                errors.append(f"引用了未启用素材：{token}")
    return list(dict.fromkeys(errors))


def system_instruction(mode: str) -> str:
    mode = normalize_mode(mode)
    fields = " / ".join(REF_FIELDS if mode == "Ref2VA" else BASE_FIELDS)
    return (
        "You are the MiniMax H3 prompt director. Rewrite the user's rough Chinese brief into a precise English H3 prompt. "
        f"Prefer these fields in this order when a structured Context-IR prompt is useful: {fields}. "
        "A clear natural-language prompt is also valid; never invent missing fields just to satisfy this preference. "
        "Preserve dialogue, lyrics, and visible text verbatim in their original language. "
        "Never invent or renumber reference labels; only use labels supplied in the material registry. "
        "Describe composition, subjects, action, camera, sound, timing, and transitions concretely."
    )
