from core.workflow_layout import sort_nodes_by_stage, stage_index


def test_stage_nodes_are_sorted_by_title_instead_of_node_id():
    nodes = [
        {"id": 35, "title": "第十阶段｜保存最终检查点"},
        {"id": 47, "title": "第一阶段｜保存视频检查点"},
        {"id": 49, "title": "第二阶段｜保存视频检查点"},
    ]
    assert [node["id"] for node in sort_nodes_by_stage(nodes)] == [47, 49, 35]
    assert stage_index("第二阶段｜保存视频检查点") == 1
    assert stage_index("第十阶段｜保存最终检查点") == 9
