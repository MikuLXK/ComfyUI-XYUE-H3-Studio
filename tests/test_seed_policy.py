from core.seed_policy import MAX_SEED, next_seed, normalize_seed_mode
from core.save_policy import normalize_collision


def test_seed_modes_are_explicit_and_reproducible():
    assert normalize_seed_mode("reuse") == "fixed"
    assert next_seed(41, "fixed") == 41
    assert next_seed(41, "increase") == 42
    assert next_seed(41, "decrease") == 40
    assert next_seed(0, "decrease") == MAX_SEED


def test_collision_labels_are_chinese_ui_values():
    assert normalize_collision("自动递增") == "increment"
    assert normalize_collision("覆盖") == "overwrite"
    assert normalize_collision("阻止") == "block"
