import json
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


def test_mask_ignores_dynamic_hud(tmp_path):
    a, b = pair(tmp_path)
    image = Image.open(b).convert("RGB")
    ImageDraw.Draw(image).rectangle((0, 0, 99, 19), fill="red")  # e.g. a clock or FPS counter
    image.save(b)
    assert compare_images(a, b, changed_fraction=0.05)["status"] == "review"
    result = compare_images(a, b, changed_fraction=0.05, masks=[[0, 0, 100, 22]])
    assert result["status"] == "within_threshold" and result["changed_fraction"] == 0


def test_masked_region_cannot_hide_black_frame(tmp_path):
    a, b = pair(tmp_path)
    image = Image.new("RGB", (100, 100), "black")
    ImageDraw.Draw(image).rectangle((0, 0, 99, 9), fill="white")  # only the HUD still draws
    image.save(b)
    result = compare_images(a, b, masks=[[0, 0, 100, 10]])
    assert result["suspected_black"] and result["status"] == "review"


def test_mostly_masked_scene_is_inconclusive(tmp_path):
    result = compare_images(*pair(tmp_path), masks=[[0, 0, 100, 80]])
    assert result["status"] == "inconclusive" and result["reason"] == "insufficient_unmasked_area"


def test_masks_use_full_image_coordinates_inside_crop(tmp_path):
    a, b = pair(tmp_path)
    image = Image.open(b).convert("RGB")
    ImageDraw.Draw(image).rectangle((60, 60, 69, 69), fill="yellow")
    image.save(b)
    result = compare_images(a, b, changed_fraction=0.01, crop=[50, 50, 100, 100], masks=[[58, 58, 72, 72]])
    assert result["status"] == "within_threshold"
    with pytest.raises(AutomationError, match="mask"):
        compare_images(a, b, crop=[50, 50, 100, 100], masks=[[0, 0, 10, 10]])


def test_difference_image_marks_changes_and_masks(tmp_path):
    a, b = pair(tmp_path)
    image = Image.open(b).convert("RGB")
    ImageDraw.Draw(image).rectangle((80, 80, 99, 99), fill="green")
    image.save(b)
    out = tmp_path / "diff.png"
    result = compare_images(a, b, masks=[[0, 0, 10, 10]], difference_output=out)
    assert result["difference_image"] == str(out) and (out.stat().st_mode & 0o777) == 0o600
    with Image.open(out) as diff:
        assert diff.getpixel((90, 90)) == (255, 0, 0)
        assert diff.getpixel((5, 5)) == (0, 64, 255)
        assert diff.getpixel((50, 50))[0] < 255
    with pytest.raises(FileExistsError):
        compare_images(a, b, difference_output=out)


def test_cli_passes_masks_and_difference_output(tmp_path, capsys):
    from automation.controller.cli import main
    a, b = pair(tmp_path)
    out = tmp_path / "diff.png"
    assert main(["compare-images", str(a), str(b), "--mask", "0", "0", "10", "10", "--difference-output", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["masks"] == [[0, 0, 10, 10]] and out.exists()
