import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
PACKAGE_NAME = "xyue_h3_video_board_test"
spec = importlib.util.spec_from_file_location(
    PACKAGE_NAME,
    ROOT / "__init__.py",
    submodule_search_locations=[str(ROOT)],
)
module = importlib.util.module_from_spec(spec)
sys.modules[PACKAGE_NAME] = module
spec.loader.exec_module(module)
from xyue_h3_video_board_test.nodes.video_board import XYUEH3VideoBoard


def test_video_board_requests_all_stage_videos_to_keep_the_chain_executable():
    assert XYUEH3VideoBoard.check_lazy_status(
        object(),
        None,
        None,
        None,
        None,
        stage1_report=None,
        stage2_report=None,
        stage3_report=None,
        stage4_report=None,
        stage5_report=None,
        studio_control={"schema": "xyue-h3/studio-control-v1", "stage_count": 5},
    ) == ["stage2_video", "stage3_video", "stage4_video", "stage5_video"]


def test_video_board_still_requires_stage_one():
    assert XYUEH3VideoBoard.check_lazy_status(
        None,
        None,
        None,
        None,
        None,
        studio_control={"schema": "xyue-h3/studio-control-v1", "stage_count": 5},
    ) == ["stage1_video", "stage2_video", "stage3_video", "stage4_video", "stage5_video"]
