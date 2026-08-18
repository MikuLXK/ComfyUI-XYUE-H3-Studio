from pathlib import Path

import pytest

from services.document_parser import extract_text, validate_document_path


def test_text_and_json_parsing(tmp_path: Path):
    text = tmp_path / "brief.txt"
    text.write_text("hello", encoding="utf-8")
    assert extract_text(text, 100)[0] == "hello"
    data = tmp_path / "brief.json"
    data.write_text('{"prompt": "hello"}', encoding="utf-8")
    assert "prompt" in extract_text(data, 100)[0]


def test_path_boundary(tmp_path: Path):
    allowed = tmp_path / "docs"; allowed.mkdir()
    good = allowed / "a.txt"; good.write_text("x", encoding="utf-8")
    assert validate_document_path(good, allowed) == good.resolve()
    with pytest.raises(ValueError):
        validate_document_path(tmp_path / "outside.txt", allowed)
