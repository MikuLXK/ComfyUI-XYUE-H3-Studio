from core.material_sessions import load_material_session, save_material_session


def test_material_session_is_isolated_and_copied():
    source = [{"kind": "image", "slot": 1, "file": "hero.png", "enabled": True}]
    save_material_session("node-101", source)
    source[0]["file"] = "changed.png"

    loaded = load_material_session("node-101")
    assert loaded[0]["file"] == "hero.png"

    loaded[0]["file"] = "mutated.png"
    assert load_material_session("node-101")[0]["file"] == "hero.png"
    assert load_material_session("node-102") == []
