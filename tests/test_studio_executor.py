import json
import importlib.util
import sys
from pathlib import Path

from services.video_checkpoints import SavedCheckpoint


def _executor_module():
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location("xyue_executor_test", root / "__init__.py", submodule_search_locations=[str(root)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return sys.modules[f"{spec.name}.nodes.studio_executor"]


class _Video:
    pass


def test_executor_uses_selected_stage_and_direct_pipeline(monkeypatch, tmp_path):
    studio_executor = _executor_module()
    calls = {}
    profile = {"schema": "xyue.h3/model-profile-v1", "mode": "文生视频模式", "video_vae": "v", "audio_vae": "a"}
    generation = {"schema": "xyue.h3/generation-profile-v1", "duration": 1, "frames": 5, "width": 32, "height": 32, "video_steps": 4, "audio_steps": 4, "sampling": {"upscale_factor": 1.5, "sigma_steps": 3, "denoise": 0.3}, "stage_name": "第一阶段", "stage_count": 1, "scheduler": "simple", "seed": 1}

    monkeypatch.setattr(studio_executor.XYUEH3ModeModelSelector, "execute", classmethod(lambda cls, **kwargs: (profile, "report", "prepared-model")))
    monkeypatch.setattr(studio_executor.XYUEH3StageGenerationProfile, "execute", classmethod(lambda cls, **kwargs: (generation, "report")))
    monkeypatch.setattr(studio_executor, "load_material_pack", lambda overrides: {"images": {"entries": []}, "videos": {"entries": []}, "audios": {"entries": []}, "registry": {"entries": []}})
    def fake_generator(cls, **kwargs):
        calls["generator"] = kwargs
        return _Video(), None, None, "{}", None
    monkeypatch.setattr(studio_executor.XYUEH3Generator, "execute", classmethod(fake_generator))
    monkeypatch.setattr(studio_executor, "save_video_with_policy", lambda *args, **kwargs: SavedCheckpoint("shot.mp4", "xyue_h3/test", str(tmp_path / "shot.mp4")))

    config = {
        "schema": "xyue-h3/studio-config-v3",
        "stage_count": 1,
        "run_stage": 1,
        "execution_stages": [1],
        "prompts": ["prompt"],
        "durations": [1],
        "transitions": ["cut"],
        "models": [{"mode": "文生视频模式", "lora_enabled": False, "lora_name": "不使用 LoRA", "attention_mode": "MiniMax H3 Kitchen Attention"}],
        "generation": {"stages": [{"aspect": "16:9", "resolution": "0.4MP|480p（864×480）", "duration": 1, "video_steps": 4, "audio_steps": 4, "scheduler": "简单稳定（推荐）", "seed": 1, "sampling": {"upscale_factor": 1.5, "sigma_steps": 3, "denoise": 0.3}}]},
    }
    result = studio_executor.XYUEH3StudioExecutor.execute(json.dumps(config, ensure_ascii=False))
    assert calls["generator"]["prepared_model"] == "prepared-model"
    assert calls["generator"]["prompt"] == "prompt"
    assert result[0].__class__ is _Video
