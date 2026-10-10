"""Offline visual evidence checks. Suspected blank frames always require review."""
import math
from PIL import Image, ImageChops, ImageFilter, ImageStat
from .device import AutomationError


def compare_images(baseline, candidate, pixel_threshold=20, changed_fraction=0.1, crop=None):
    if not isinstance(pixel_threshold, int) or not 0 <= pixel_threshold <= 255:
        raise AutomationError("invalid_pixel_threshold")
    if not math.isfinite(changed_fraction) or not 0 <= changed_fraction <= 1:
        raise AutomationError("invalid_changed_fraction")
    with Image.open(baseline) as source, Image.open(candidate) as target:
        a, b = source.convert("RGB"), target.convert("RGB")
    if a.size != b.size:
        return {"status": "inconclusive", "reason": "resolution_mismatch", "baseline_size": a.size, "candidate_size": b.size}
    if crop is not None:
        if (len(crop) != 4 or any(type(v) is not int for v in crop)
                or not 0 <= crop[0] < crop[2] <= a.width or not 0 <= crop[1] < crop[3] <= a.height):
            raise AutomationError("invalid_game_region_crop")
        a, b = a.crop(crop), b.crop(crop)
    luminance = ImageStat.Stat(b.convert("L"))
    black = luminance.mean[0] < 3 and luminance.stddev[0] < 2
    uniform = max(ImageStat.Stat(b).stddev) < 1
    # Small antialiasing differences should not dominate comparison.
    delta = ImageChops.difference(a.filter(ImageFilter.GaussianBlur(1)), b.filter(ImageFilter.GaussianBlur(1)))
    channels = delta.split()
    maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    histogram = maximum.histogram()
    fraction = sum(histogram[pixel_threshold + 1:]) / (a.width * a.height)
    return {"status": "review" if black or uniform or fraction > changed_fraction else "within_threshold",
            "suspected_black": black, "suspected_uniform": uniform, "changed_fraction": fraction,
            "pixel_threshold": pixel_threshold, "allowed_changed_fraction": changed_fraction,
            "mean_channel_difference": sum(ImageStat.Stat(delta).mean) / 3,
            "crop": crop, "note": "A dark/loading scene or dynamic content can explain a difference; this is not a source regression verdict."}
