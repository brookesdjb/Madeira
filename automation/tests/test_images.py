from PIL import Image, ImageDraw
import pytest
from automation.controller.device import AutomationError
from automation.controller.images import compare_images


def pair(tmp_path):
    image = Image.new("RGB", (100, 100), "white")
    ImageDraw.Draw(image).rectangle((25, 25, 75, 75), fill="blue")
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    image.save(a); image.save(b)
    return a, b


def test_identical_scene_passes(tmp_path):
    assert compare_images(*pair(tmp_path))["status"] == "within_threshold"


def test_black_surface_is_review_even_when_baseline_black(tmp_path):
    a, b = pair(tmp_path)
    for path in (a, b): Image.new("RGB", (100, 100), "black").save(path)
    result = compare_images(a, b)
    assert result["suspected_black"] and result["status"] == "review"


def test_resolution_change_is_inconclusive(tmp_path):
    a, b = pair(tmp_path)
    Image.new("RGB", (50, 50)).save(b)
    assert compare_images(a, b)["status"] == "inconclusive"


def test_large_rendering_change_is_detected(tmp_path):
    a, b = pair(tmp_path)
    Image.new("RGB", (100, 100), "red").save(b)
    result = compare_images(a, b)
    assert result["changed_fraction"] > .5 and result["status"] == "review"


def test_invalid_crop_rejected(tmp_path):
    with pytest.raises(AutomationError, match="crop"):
        compare_images(*pair(tmp_path), crop=[-1, 0, 99, 99])
