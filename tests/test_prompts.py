from core.h3_prompt import compile_draft, normalize_prompt_layout, validate_prompt


def test_base_and_ref_field_order():
    base = "integrated_multimodal_description: A shot.\noverall_soundscape: Wind.\nnon_diegetic_music: None."
    assert not validate_prompt(base, "T2VA", 5, strict_fields=True)
    ref = "subject_definitions: <Picture 1>.\nsummary: A shot.\nretention_analysis: Keep identity.\ndetailed_description: A shot.\noverall_soundscape: Wind.\nnon_diegetic_music: None."
    registry = {"token_to_alias": {"<Picture 1>": "@hero"}}
    assert not validate_prompt(ref, "Ref2VA", 5, registry, strict_fields=True)


def test_keyframe_instruction_and_case_normalization():
    text, _ = compile_draft("从第一帧开始，<picture 1>向前移动。", "I2VA", None, 5)
    assert "0.00 seconds" in text and "<Picture 1>" in text


def test_invalid_token_is_reported():
    errors = validate_prompt("integrated_multimodal_description: <Picture 2>\noverall_soundscape: x\nnon_diegetic_music: y", "T2VA", 5, {"token_to_alias": {"<Picture 1>": "@a"}})
    assert any("Picture 2" in error for error in errors)


def test_chinese_mode_labels_are_accepted():
    text, _ = compile_draft("integrated_multimodal_description: A shot.\noverall_soundscape: Wind.\nnon_diegetic_music: None.", "文生视频模式", None, 5)
    assert "integrated_multimodal_description" in text
    ref = "subject_definitions: <Picture 1>.\nsummary: A shot.\nretention_analysis: Keep identity.\ndetailed_description: A shot.\noverall_soundscape: Wind.\nnon_diegetic_music: None."
    errors = validate_prompt(ref, "多参考模式", 5, {"token_to_alias": {"<Picture 1>": "@hero"}})
    assert not errors


def test_official_field_layout_uses_real_blank_lines():
    source = "integrated_multimodal_description: A shot.\\noverall_soundscape: Wind.\\nnon_diegetic_music: None."
    normalized = normalize_prompt_layout(source, "文生视频模式")
    assert "\\n" not in normalized
    assert "integrated_multimodal_description:\nA shot.\n\noverall_soundscape:\nWind." in normalized


def test_h3_accepts_natural_language_without_context_ir_fields():
    natural = "A woman walks through a rainy alley, the camera slowly tracks left, with soft room tone."
    assert validate_prompt(natural, "Ref2VA", 5) == []


def test_natural_language_passes_by_default_but_references_are_checked():
    assert validate_prompt("雨巷里一个女人缓步前行，镜头缓缓左移，环境声轻柔。", "多参考模式", 5) == []
    errors = validate_prompt("A rainy alley, use <Picture 2>.", "T2VA", 5, {"token_to_alias": {"<Picture 1>": "@a"}})
    assert any("Picture 2" in error for error in errors)


def test_keyframe_placeholders_are_valid_before_runtime_images_exist():
    registry = {"alias_to_token": {}, "token_to_alias": {}}
    i2va, _ = compile_draft("Continue from <Picture 1>.", "I2VA", registry, 4)
    fl2va, _ = compile_draft("Move from <Picture 1> to <Picture 2>.", "FL2VA", registry, 4)

    assert "<Picture 1>" in i2va
    assert "<Picture 1>" in fl2va
    assert "<Picture 2>" in fl2va
    assert validate_prompt(i2va, "I2VA", 4, registry, strict_fields=False) == []
    assert validate_prompt(fl2va, "FL2VA", 4, registry, strict_fields=False) == []


def test_keyframe_aliases_compile_without_material_registry():
    registry = {
        "alias_to_token": {"@原始角色图": "<Picture 1>"},
        "token_to_alias": {"<Picture 1>": "@原始角色图"},
    }
    compiled, used = compile_draft("从@上一段尾帧继续。", "I2VA", registry, 4)

    assert "<Picture 1>" in compiled
    assert used == ("@上一段尾帧",)
    try:
        compile_draft("继续使用@原始角色图。", "I2VA", registry, 4)
    except ValueError as error:
        assert "无效素材引用" in str(error)
    else:
        raise AssertionError("I2VA must not treat Ref2VA aliases as native keyframes")


def test_i2va_tail_alias_refers_to_the_connected_previous_video_tail():
    compiled, used = compile_draft("从@尾帧继续动作。", "I2VA", None, 4)

    assert "<Picture 1>" in compiled
    assert used == ("@尾帧",)


def test_ref_mode_still_rejects_unavailable_picture_placeholder():
    registry = {"alias_to_token": {}, "token_to_alias": {}}
    try:
        compile_draft("Use <Picture 1>.", "Ref2VA", registry, 4)
    except ValueError as error:
        assert "无效素材引用" in str(error)
    else:
        raise AssertionError("Ref2VA must only accept enabled material references")
