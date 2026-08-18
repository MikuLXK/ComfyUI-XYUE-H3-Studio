from services.prompt_api import _extract_response
from services.api_profiles import _timeout_value


def test_response_shapes():
    assert _extract_response({"output_text": "ok"}, "responses") == "ok"
    assert _extract_response({"output": [{"content": [{"text": "ok"}]}]}, "responses") == "ok"
    assert _extract_response({"choices": [{"message": {"content": "ok"}}]}, "chat_completions") == "ok"
    assert _extract_response({"choices": [{"message": {"content": [{"text": "a"}, {"text": "b"}]}}]}, "chat_completions") == "a\nb"


def test_unlimited_timeout_value():
    assert _timeout_value(None) is None
    assert _timeout_value("") is None
    assert _timeout_value(30) == 30
