"""Remove demo prompt/title data from the generated Studio bundle."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]


def clean_bundle(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    text, count = re.subn(
        r"title:e===1\?.*?,slate:",
        'title:"",slate:',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"stage title default not found in {path}")

    text = text.replace("prompt:e===1?jt:``", 'prompt:``', 1)

    start = text.find("jt=`", 200_000)
    end = text.find("`;function Mt", start)
    if start < 0 or end < 0:
        raise RuntimeError(f"stage prompt default not found in {path}")
    text = text[:start] + "jt=``" + text[end + 1 :]

    modal_start = text.find("function ct({open:")
    modal_end = text.find("function lt({open:", modal_start)
    if modal_start < 0 or modal_end < 0:
        raise RuntimeError(f"config modal not found in {path}")
    modal = text[modal_start:modal_end]
    modal, title_count = re.subn(r'"stage_titles":\s*\[[^]]*\]', '"stage_titles":[""]', modal, count=1)
    modal, prompt_count = re.subn(r'"prompts":\s*\["integrated_multimodal_description:.*?"\]', '"prompts":[""]', modal, count=1, flags=re.S)
    if title_count != 1 or prompt_count != 1:
        raise RuntimeError(f"config modal defaults not found in {path}")
    text = text[:modal_start] + modal + text[modal_end:]
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    bundles = sorted((ROOT / "studio_ui" / "assets").glob("index-*.js"))
    if not bundles:
        raise SystemExit("Studio bundle not found")
    for bundle in bundles:
        clean_bundle(bundle)
        print(bundle)
