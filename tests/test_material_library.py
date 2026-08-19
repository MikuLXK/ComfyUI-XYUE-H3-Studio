from core.material_library import media_kind, scan_material_library


def test_material_library_lists_supported_media_recursively(tmp_path):
    (tmp_path / "characters").mkdir()
    (tmp_path / "characters" / "hero.PNG").write_bytes(b"image")
    (tmp_path / "shot.mp4").write_bytes(b"video")
    (tmp_path / "voice.wav").write_bytes(b"audio")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")

    entries = scan_material_library(tmp_path)

    assert {(entry["kind"], entry["file"]) for entry in entries} == {
        ("image", "characters/hero.PNG"),
        ("video", "shot.mp4"),
        ("audio", "voice.wav"),
    }
    assert media_kind(tmp_path / "notes.txt") is None
