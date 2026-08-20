import pytest

from core.multi_stage_config import parse_multi_stage_config


def test_cloud_config_parser_keeps_model_policy_external():
    config = parse_multi_stage_config({
        "schema": "xyue.h3.multi-stage-cloud-config/v1",
        "stage_count": 1,
        "prompts": ["prompt"],
        "generation": {"stages": [{"duration": 5}]},
        "acceleration": {"enabled": False},
    })
    assert config["stage_count"] == 1
    assert config["generation"]["stages"][0]["duration"] == 5


def test_cloud_config_rejects_models_and_lora():
    with pytest.raises(ValueError):
        parse_multi_stage_config({
            "schema": "xyue.h3.multi-stage-cloud-config/v1",
            "stage_count": 1,
            "prompts": ["prompt"],
            "models": [{}],
            "generation": {"stages": [{"duration": 5}]},
        })
