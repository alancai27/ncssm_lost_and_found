#!/usr/bin/env python3
"""
Install a campus photo as a page background.

    python3 scripts/set_background.py durham    ~/Downloads/durham.jpg
    python3 scripts/set_background.py morganton ~/Downloads/morganton.jpg

Just saved the photo out of a chat or a browser? Use --latest and it grabs
the newest image sitting in ~/Downloads:

    python3 scripts/set_background.py durham --latest

Resizes and writes static/assets/<campus>-bg.webp. Hand it the original --
the page lays a dark scrim over the photo in CSS, so there is no need to
darken it yourself.
"""

import os
import sys

from PIL import Image, ImageOps

# Backgrounds are scaled to fill the viewport, so a source narrower than a
# typical display gets upscaled by the browser -- usually with cheap bilinear
# filtering, which reads as blur. Resampling to this width ourselves with
# Lanczos plus a light unsharp mask gives the browser a 1:1-or-better image to
# work from. It cannot invent detail the source never had; it just stops us
# losing more of it than necessary.
TARGET_WIDTH = 2400
# WebP at 82 is visually on par with JPEG at 92 here and roughly half the
# bytes. Both campus images load on every page, so the saving is per-visit.
QUALITY = 82
EXTS = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "static", "assets")


def newest_download():
    folder = os.path.expanduser("~/Downloads")
    if not os.path.isdir(folder):
        return None
    images = [
        os.path.join(folder, n)
        for n in os.listdir(folder)
        if n.lower().endswith(EXTS) and not n.startswith(".")
    ]
    return max(images, key=os.path.getmtime) if images else None


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("durham", "morganton"):
        print(__doc__.strip())
        return 1

    campus, source = sys.argv[1], sys.argv[2]

    if source == "--latest":
        source = newest_download()
        if not source:
            print("No images found in ~/Downloads.")
            return 1
        print(f"Using newest download: {source}")
    else:
        source = os.path.expanduser(source)

    if not os.path.exists(source):
        print(f"No such file: {source}")
        return 1

    try:
        img = ImageOps.exif_transpose(Image.open(source)).convert("RGB")
    except Exception as exc:
        print(f"Could not read that image: {exc}")
        if source.lower().endswith(".heic"):
            print("HEIC needs an extra package:  pip install pillow-heif")
        return 1

    before = img.size
    upscaled = img.width < TARGET_WIDTH

    if img.width != TARGET_WIDTH:
        img = img.resize(
            (TARGET_WIDTH, round(img.height * TARGET_WIDTH / img.width)), Image.LANCZOS
        )

    if "--no-sharpen" not in sys.argv:
        from PIL import ImageFilter

        # Gentler on an upscale (no real detail to bring out, and aggressive
        # sharpening makes Lanczos ringing obvious) than on a downscale.
        if upscaled:
            img = img.filter(ImageFilter.UnsharpMask(radius=1.6, percent=85, threshold=3))
        else:
            img = img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=110, threshold=3))

    os.makedirs(ASSETS, exist_ok=True)
    dest = os.path.join(ASSETS, f"{campus}-bg.webp")
    img.save(dest, "WEBP", quality=QUALITY, method=6)

    # Drop a stale JPEG from an older run so the CSS never has two candidates.
    old_jpg = os.path.join(ASSETS, f"{campus}-bg.jpg")
    if os.path.exists(old_jpg):
        os.remove(old_jpg)

    verb = "upscaled" if upscaled else "resized"
    print(f"{campus}: {before[0]}x{before[1]} -> {img.width}x{img.height} ({verb})")
    if upscaled:
        print("  NOTE: the source was smaller than the target. This sharpens the")
        print("  result but cannot add detail -- a higher-resolution original is")
        print("  the only real fix.")
    print(f"wrote {os.path.relpath(dest, ROOT)} ({os.path.getsize(dest) / 1024:.0f} KB)")

    # White Montserrat sits over the top-left of this image, so check whether
    # the CSS scrim is heavy enough for it to stay readable.
    from PIL import ImageStat

    grey = img.convert("L")
    overall = ImageStat.Stat(grey).mean[0]
    w, h = grey.size
    text_zone = ImageStat.Stat(grey.crop((0, 0, int(w * 0.6), int(h * 0.7)))).mean[0]

    print(f"\nbrightness: {overall:.0f}/255 overall, {text_zone:.0f}/255 behind the text")
    if text_zone < 90:
        print("  Dark enough -- the default scrim is fine.")
    elif text_zone < 130:
        print("  Middling. Readable, but check it; if the heading looks washed")
        print("  out, raise the rgba(...) alphas on .bg-%s in static/main.css." % campus)
    else:
        print("  BRIGHT. White text will likely be hard to read. Raise the")
        print("  rgba(...) alpha values on .bg-%s in static/main.css" % campus)
        print("  (try 0.55 / 0.40 / 0.62 instead of 0.34 / 0.16 / 0.46).")

    print("\nReload the page -- no restart needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
