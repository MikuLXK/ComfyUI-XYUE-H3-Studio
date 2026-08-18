from core.resolution import RESOLUTION_PRESETS_16_9, align_duration, native_canvas, preset_canvas


def test_all_locked_16_9_resolutions():
    for name, expected in RESOLUTION_PRESETS_16_9.items():
        assert preset_canvas("16:9", name) == expected


def test_all_aspects_are_32_aligned():
    for aspect in ("16:9", "9:16", "4:3", "3:4", "1:1", "21:9"):
        width, height = native_canvas(aspect)
        assert width % 32 == 0 and height % 32 == 0


def test_frame_grid():
    for seconds in range(1, 16):
        frames, actual = align_duration(seconds)
        assert frames % 17 == 5
        assert actual >= seconds
