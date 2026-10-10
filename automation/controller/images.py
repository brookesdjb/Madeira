"""Offline visual evidence checks. Suspected blank frames always require review."""
import math
import os
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat
from .device import AutomationError

MAX_MASKS = 32
# Below this, masks hide too much of the scene for a difference to mean anything.
MIN_UNMASKED_FRACTION = 0.25


def _rectangle(value, bounds, error):
    if (not isinstance(value, (list, tuple)) or len(value) != 4 or any(type(v) is not int for v in value)
            or not bounds[0] <= value[0] < value[2] <= bounds[2] or not bounds[1] <= value[1] < value[3] <= bounds[3]):
        raise AutomationError(error)
    return tuple(value)


def _write_difference(path, candidate, changed, mask):
    # Dimmed candidate, changed pixels red, ignored regions blue; never overwrite evidence.
    view = candidate.convert("L").point(lambda v: v * 2 // 5).convert("RGB")
    view.paste((255, 0, 0), mask=changed)
    view.paste((0, 64, 255), mask=ImageChops.invert(mask))
    with open(path, "xb") as target:
        os.fchmod(target.fileno(), 0o600)
        view.save(target, "PNG")


def compare_images(baseline, candidate, pixel_threshold=20, changed_fraction=0.1, crop=None, masks=None, difference_output=None):
    if not isinstance(pixel_threshold, int) or not 0 <= pixel_threshold <= 255:
        raise AutomationError("invalid_pixel_threshold")
    if not math.isfinite(changed_fraction) or not 0 <= changed_fraction <= 1:
        raise AutomationError("invalid_changed_fraction")
    if masks is not None and (not isinstance(masks, (list, tuple)) or len(masks) > MAX_MASKS):
        raise AutomationError("invalid_ignore_masks")
    with Image.open(baseline) as source, Image.open(candidate) as target:
        a, b = source.convert("RGB"), target.convert("RGB")
    if a.size != b.size:
        return {"status": "inconclusive", "reason": "resolution_mismatch", "baseline_size": a.size, "candidate_size": b.size,
                "difference_image": None}
    region = (0, 0, a.width, a.height)
    if crop is not None:
        region = _rectangle(crop, region, "invalid_game_region_crop")
        a, b = a.crop(region), b.crop(region)
    # Masks use full-image coordinates so one calibration works with or without a crop.
    mask = Image.new("L", a.size, 255)
    draw = ImageDraw.Draw(mask)
    for item in masks or ():
        x0, y0, x1, y1 = _rectangle(item, region, "invalid_ignore_mask")
        draw.rectangle((x0 - region[0], y0 - region[1], x1 - region[0] - 1, y1 - region[1] - 1), fill=0)
    unmasked = mask.histogram()[255]
    unmasked_fraction = unmasked / (a.width * a.height)
    if unmasked_fraction < MIN_UNMASKED_FRACTION:
        return {"status": "inconclusive", "reason": "insufficient_unmasked_area", "unmasked_fraction": unmasked_fraction,
                "crop": crop, "masks": masks, "difference_image": None}
    luminance = ImageStat.Stat(b.convert("L"), mask)
    black = luminance.mean[0] < 3 and luminance.stddev[0] < 2
    uniform = max(ImageStat.Stat(b, mask).stddev) < 1
    # Small antialiasing differences should not dominate comparison.
    delta = ImageChops.difference(a.filter(ImageFilter.GaussianBlur(1)), b.filter(ImageFilter.GaussianBlur(1)))
    channels = delta.split()
    maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    maximum = ImageChops.multiply(maximum, mask)
    fraction = sum(maximum.histogram()[pixel_threshold + 1:]) / unmasked
    status = "review" if black or uniform or fraction > changed_fraction else "within_threshold"
    written = None
    if difference_output is not None:
        changed = maximum.point(lambda v: 255 if v > pixel_threshold else 0)
        _write_difference(difference_output, b, changed, mask)
        written = str(difference_output)
    return {"status": status,
            "suspected_black": black, "suspected_uniform": uniform, "changed_fraction": fraction,
            "pixel_threshold": pixel_threshold, "allowed_changed_fraction": changed_fraction,
            "mean_channel_difference": sum(ImageStat.Stat(delta, mask).mean) / 3,
            "crop": crop, "masks": masks, "unmasked_fraction": unmasked_fraction, "difference_image": written,
            "note": "A dark/loading scene or dynamic content can explain a difference; this is not a source regression verdict."}
