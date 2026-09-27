import pytest
from slides import color


def test_hex_round_trips():
    assert color.to_hex(*color.to_rgb("#a5d75f")) == "#a5d75f"


def test_oklab_round_trips():
    for value in ("#000000", "#ffffff", "#a5d75f", "#0d1e1c", "#980c0c"):
        assert color.from_oklab(*color.to_oklab(value)) == value


def test_oklch_round_trips():
    for value in ("#a5d75f", "#0d1e1c", "#5ce1e6"):
        assert color.from_oklch(*color.to_oklch(value)) == value


def test_luminance_endpoints():
    assert color.luminance("#000000") == pytest.approx(0.0, abs=1e-6)
    assert color.luminance("#ffffff") == pytest.approx(1.0, abs=1e-6)


def test_contrast_is_symmetric_and_bounded():
    assert color.contrast("#000000", "#ffffff") == pytest.approx(21.0, abs=0.01)
    assert color.contrast("#ffffff", "#000000") == pytest.approx(21.0, abs=0.01)
    assert color.contrast("#a5d75f", "#a5d75f") == pytest.approx(1.0, abs=1e-6)


def test_delta_e_orders_by_perceptual_distance():
    near = color.delta_e("#00a2ff", "#0093e8")
    far = color.delta_e("#00a2ff", "#a5d75f")
    assert near < far
    assert near < 0.08


def test_mix_endpoints_and_midpoint():
    assert color.mix("#000000", "#ffffff", 0.0) == "#000000"
    assert color.mix("#000000", "#ffffff", 1.0) == "#ffffff"
    middle = color.mix("#000000", "#ffffff", 0.5)
    assert 0.1 < color.luminance(middle) < 0.4


def test_with_contrast_lightens_against_a_dark_ground():
    fixed = color.with_contrast("#1a3330", "#0d1e1c", 4.5)
    assert color.contrast(fixed, "#0d1e1c") >= 4.5


def test_with_contrast_darkens_against_a_light_ground():
    fixed = color.with_contrast("#eeeeee", "#ffffff", 4.5)
    assert color.contrast(fixed, "#ffffff") >= 4.5


def test_with_contrast_holds_hue():
    before = color.to_oklch("#00a2ff")[2]
    after = color.to_oklch(color.with_contrast("#00a2ff", "#ffffff", 4.5))[2]
    assert abs(before - after) < 2.0


def test_with_contrast_is_a_no_op_when_already_sufficient():
    assert color.with_contrast("#ffffff", "#000000", 4.5) == "#ffffff"
