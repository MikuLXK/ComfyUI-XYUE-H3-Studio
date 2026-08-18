from core.materials import build_audio_pack, build_image_pack, build_material_pack, build_video_pack, compile_mentions, filename_stem
from core.reference_limits import continuation_image_action, reference_counts, validate_reference_limits


def item(filename, kind="image", enabled=True, numbered=False, audio=None):
    return {"filename": filename, "enabled": enabled, "numbered_alias": numbered, "audio": audio, "kind": kind}


def test_alias_normalization_and_collision():
    assert filename_stem("目录/a b?.png") == "a_b"
    pack, _ = build_image_pack([item("a.png"), item("a.jpg"), item("disabled.png", enabled=False), item("c.png", numbered=True)])
    assert [entry["token"] for entry in pack["entries"]] == ["<Picture 1>", "<Picture 2>", "<Picture 3>"]
    assert pack["entries"][0]["alias"] == "@a"
    assert pack["entries"][1]["alias"] == "@a_2"
    assert pack["entries"][2]["alias"] == "@图片3"


def test_audio_numbering_video_soundtracks_before_standalone():
    video, _ = build_video_pack([item("clip.mp4", "video", audio={"waveform": 1})])
    audio, _ = build_audio_pack([item("voice.wav", "audio")])
    material, registry = build_material_pack(None, video, audio)
    assert video["entries"][0]["audio_token"] == "<Audio 1>"
    assert material["audios"]["entries"][0]["token"] == "<Audio 2>"
    assert any(entry.get("media_kind") == "video_audio" for entry in registry["entries"])


def test_maximum_slots_and_disabled_compaction():
    images = [item(f"frame_{index}.png", enabled=index != 3) for index in range(1, 11)]
    videos = [item(f"clip_{index}.mp4", "video", enabled=index != 2) for index in range(1, 5)]
    audios = [item(f"voice_{index}.wav", "audio", enabled=index != 2) for index in range(1, 5)]
    image_pack, _ = build_image_pack(images)
    video_pack, _ = build_video_pack(videos)
    audio_pack, _ = build_audio_pack(audios)
    assert image_pack["count"] == 9
    assert video_pack["count"] == 3
    assert audio_pack["count"] == 3
    assert [entry["token"] for entry in image_pack["entries"]] == [f"<Picture {index}>" for index in range(1, 10)]
    assert [entry["token"] for entry in video_pack["entries"]] == ["<Video 1>", "<Video 2>", "<Video 3>"]


def test_mentions_compile_and_invalid_direct_token():
    pack, aliases = build_image_pack([item("hero.png")])
    registry = {"alias_to_token": aliases, "token_to_alias": pack["token_to_alias"]}
    assert compile_mentions("@hero and <picture 1>", registry)[0] == "<Picture 1> and <Picture 1>"
    try:
        compile_mentions("<Picture 2>", registry)
    except ValueError as exc:
        assert "Picture 2" in str(exc)
    else:
        raise AssertionError("invalid direct token was accepted")


def test_numbered_mentions_are_canonical_and_keep_punctuation():
    registry = {
        "alias_to_token": {"@角色图": "<Picture 1>"},
        "token_to_alias": {"<Picture 1>": "@角色图", "<Picture 9>": "@最后一张"},
    }
    compiled, _ = compile_mentions("@图片1。@image_9!", registry)
    assert compiled == "<Picture 1>。<Picture 9>!"


def test_ref2va_mixed_file_limit_and_video_soundtrack_counting():
    images, _ = build_image_pack([item(f"frame_{index}.png") for index in range(1, 9)])
    videos, _ = build_video_pack([item("clip.mp4", "video", audio={"waveform": 1})])
    audios, _ = build_audio_pack([item("voice.wav", "audio")])
    counts = validate_reference_limits(images, videos, audios)
    assert counts == {"pictures": 8, "videos": 1, "audios": 1, "mixed": 10}
    assert reference_counts(images, videos, audios)["mixed"] == 10

    full_images, _ = build_image_pack([item(f"full_{index}.png") for index in range(1, 10)])
    full_videos, _ = build_video_pack([item(f"clip_{index}.mp4", "video") for index in range(1, 4)])
    full_audios, _ = build_audio_pack([item("too_many.wav", "audio")])
    try:
        validate_reference_limits(full_images, full_videos, full_audios)
    except ValueError as exc:
        assert "混合素材 13/12" in str(exc)
    else:
        raise AssertionError("13 mixed references were accepted")


def test_image_pack_records_physical_source_slot_after_compaction():
    source_items = []
    for slot in range(1, 7):
        value = item(f"slot_{slot}.png", enabled=slot in {1, 3, 6})
        value["source_slot"] = slot
        source_items.append(value)
    pack, _ = build_image_pack(source_items)
    assert [(entry["source_slot"], entry["token"]) for entry in pack["entries"]] == [
        (1, "<Picture 1>"),
        (3, "<Picture 2>"),
        (6, "<Picture 3>"),
    ]


def test_continuation_replacement_keeps_mixed_count_at_twelve():
    images, _ = build_image_pack([item(f"image_{index}.png") for index in range(1, 10)])
    videos, _ = build_video_pack([item(f"video_{index}.mp4", "video") for index in range(1, 4)])
    before = validate_reference_limits(images, videos, None)
    replacement_items = list(images["entries"][:-1]) + [item("上一段尾帧.png")]
    replaced_images, _ = build_image_pack(replacement_items)
    after = validate_reference_limits(replaced_images, videos, None)
    assert before["mixed"] == after["mixed"] == 12
    assert replaced_images["entries"][-1]["token"] == "<Picture 9>"


def test_continuation_appends_until_picture_nine_then_reuses_last_slot():
    one, _ = build_image_pack([item("only.png")])
    eight, _ = build_image_pack([item(f"eight_{index}.png") for index in range(1, 9)])
    nine, _ = build_image_pack([item(f"nine_{index}.png") for index in range(1, 10)])
    assert continuation_image_action(one, None, None) == "append_picture"
    assert continuation_image_action(eight, None, None) == "append_picture"
    assert continuation_image_action(nine, None, None) == "replace_last_picture"


def test_continuation_does_not_silently_replace_when_only_mixed_limit_is_full():
    images, _ = build_image_pack([item(f"image_{index}.png") for index in range(1, 9)])
    videos, _ = build_video_pack([item(f"video_{index}.mp4", "video") for index in range(1, 4)])
    audios, _ = build_audio_pack([item("voice.wav", "audio")])
    try:
        continuation_image_action(images, videos, audios)
    except ValueError as exc:
        assert "混合素材 12/12" in str(exc)
        assert "另需预留 1 项" in str(exc)
    else:
        raise AssertionError("a thirteenth mixed reference was accepted")
