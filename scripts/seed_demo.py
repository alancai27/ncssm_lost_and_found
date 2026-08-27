#!/usr/bin/env python3
"""
Fill the database with a few placeholder items so you can see the UI
before anyone has posted anything real.

    python3 scripts/seed_demo.py          # add demo items
    python3 scripts/seed_demo.py --clear  # remove them again
"""

import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "uploads")

DEMO = [
    dict(stem="demo_bottle", shape="bottle", bg=(226, 232, 236), fg=(31, 66, 122),
         title="Navy Hydro Flask", category="bottle", color="navy blue", brand="Hydro Flask",
         tags=["water bottle", "flask", "thermos", "navy", "blue", "stickers", "metal", "dented"],
         ai_description="A tall navy blue insulated steel water bottle with a black flip-top lid. "
                        "Two faded stickers on the front and a dent near the base.",
         note="Left on a bench outside. Front desk has it.",
         location="Bryan lobby", found_at="2026-08-24",
         finder_name="Jordan", finder_contact="front desk"),
    dict(stem="demo_bag", shape="bag", bg=(238, 234, 226), fg=(46, 48, 54),
         title="Black JanSport backpack", category="bag", color="black", brand="JanSport",
         tags=["backpack", "bag", "jansport", "black", "school bag", "zipper", "keychain"],
         ai_description="A worn black JanSport backpack with grey straps and a small enamel pin "
                        "on the front pocket. One zipper pull is missing.",
         note="Found under a table in the study room.",
         location="1st Hill study room", found_at="2026-08-25",
         finder_name="Priya", finder_contact="pgupta@example.edu"),
    dict(stem="demo_buds", shape="buds", bg=(240, 240, 244), fg=(250, 250, 250),
         title="White wireless earbuds case", category="headphones", color="white",
         brand="Apple", tags=["airpods", "earbuds", "headphones", "white", "case", "charging case"],
         ai_description="A small white wireless earbud charging case, scuffed on one corner. "
                        "Both earbuds are inside.",
         note=None, location="PEC weight room", found_at="2026-08-25",
         finder_name=None, finder_contact="front desk"),
    dict(stem="demo_calc", shape="calc", bg=(232, 236, 230), fg=(24, 28, 34),
         title="TI-84 graphing calculator", category="electronics", color="black",
         brand="Texas Instruments", tags=["calculator", "ti84", "graphing", "black", "math"],
         ai_description="A black TI-84 Plus graphing calculator, no slide cover. Initials are "
                        "written in silver marker on the back.",
         note="Initials on the back — tell me what they are and it's yours.",
         location="Watts 210", found_at="2026-08-23",
         finder_name="Mr. Alvarez", finder_contact="malvarez@example.edu"),
    dict(stem="demo_jacket", shape="jacket", bg=(228, 231, 238), fg=(122, 32, 40),
         title="Maroon zip-up hoodie", category="clothing", color="maroon", brand=None,
         tags=["hoodie", "sweatshirt", "jacket", "maroon", "red", "zip up", "drawstring"],
         ai_description="A maroon zip-up hoodie, adult medium, with white drawstrings and a "
                        "small unreadable logo on the left chest.",
         note=None, location="Ground floor Reynolds", found_at="2026-08-22",
         finder_name="Sam", finder_contact="scho@example.edu"),
    dict(stem="demo_keys", shape="keys", bg=(236, 233, 226), fg=(140, 142, 148),
         title="Keys on a blue lanyard", category="keys", color="blue, silver", brand=None,
         tags=["keys", "keychain", "lanyard", "blue", "dorm key", "fob"],
         ai_description="Three keys and a small plastic fob on a blue fabric lanyard. "
                        "One key has a green rubber cover.",
         note="Turned in to residential life.",
         location="Between Hunt and Reynolds", found_at="2026-08-26",
         finder_name=None, finder_contact="Residential Life office"),
]


def draw(shape, bg, fg, size=(1000, 750)):
    """Rough flat illustrations -- placeholders for real photos."""
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    cx, cy = size[0] // 2, size[1] // 2

    if shape == "bottle":
        d.rounded_rectangle([cx - 90, cy - 210, cx + 90, cy + 240], 45, fill=fg)
        d.rounded_rectangle([cx - 45, cy - 275, cx + 45, cy - 195], 18, fill=(40, 40, 44))
        d.rounded_rectangle([cx - 55, cy - 90, cx + 55, cy + 10], 8, fill=(255, 255, 255))
        d.ellipse([cx - 40, cy + 70, cx + 40, cy + 150], fill=(255, 255, 255))
    elif shape == "bag":
        d.rounded_rectangle([cx - 170, cy - 150, cx + 170, cy + 230], 55, fill=fg)
        d.rounded_rectangle([cx - 130, cy + 20, cx + 130, cy + 190], 30, fill=(70, 72, 80))
        d.arc([cx - 120, cy - 300, cx - 20, cy - 60], 200, 340, fill=(90, 92, 100), width=26)
        d.arc([cx + 20, cy - 300, cx + 120, cy - 60], 200, 340, fill=(90, 92, 100), width=26)
        d.ellipse([cx + 60, cy - 90, cx + 110, cy - 40], fill=(200, 60, 60))
    elif shape == "buds":
        d.rounded_rectangle([cx - 150, cy - 110, cx + 150, cy + 110], 60,
                            fill=fg, outline=(205, 205, 212), width=4)
        d.line([cx - 150, cy - 20, cx + 150, cy - 20], fill=(215, 215, 222), width=5)
        d.ellipse([cx - 70, cy + 30, cx - 20, cy + 80], fill=(228, 228, 234))
        d.ellipse([cx + 20, cy + 30, cx + 70, cy + 80], fill=(228, 228, 234))
    elif shape == "calc":
        d.rounded_rectangle([cx - 120, cy - 240, cx + 120, cy + 240], 24, fill=fg)
        d.rounded_rectangle([cx - 90, cy - 200, cx + 90, cy - 70], 8, fill=(150, 170, 140))
        for row in range(5):
            for col in range(5):
                x = cx - 92 + col * 38
                y = cy - 30 + row * 52
                d.rounded_rectangle([x, y, x + 30, y + 38], 6, fill=(70, 74, 84))
    elif shape == "jacket":
        d.polygon([(cx - 200, cy - 130), (cx - 90, cy - 190), (cx + 90, cy - 190),
                   (cx + 200, cy - 130), (cx + 165, cy + 30), (cx + 120, cy + 10),
                   (cx + 120, cy + 235), (cx - 120, cy + 235), (cx - 120, cy + 10),
                   (cx - 165, cy + 30)], fill=fg)
        d.line([cx, cy - 175, cx, cy + 235], fill=(230, 230, 235), width=7)
        d.line([cx - 34, cy - 178, cx - 34, cy - 120], fill=(245, 245, 248), width=9)
        d.line([cx + 34, cy - 178, cx + 34, cy - 120], fill=(245, 245, 248), width=9)
    elif shape == "keys":
        d.line([cx - 30, cy - 250, cx - 30, cy - 40], fill=(40, 90, 190), width=46)
        d.ellipse([cx - 62, cy - 72, cx + 2, cy - 8], outline=(150, 152, 158), width=9)
        for i, angle in enumerate((-46, 0, 46)):
            x = cx - 30 + angle
            d.rounded_rectangle([x - 17, cy + 10, x + 17, cy + 190], 14, fill=fg)
            d.ellipse([x - 26, cy - 2, x + 26, cy + 50], fill=fg)
            d.ellipse([x - 10, cy + 14, x + 10, cy + 34], fill=bg)
            if i == 2:
                d.rounded_rectangle([x - 20, cy + 120, x + 20, cy + 195], 12, fill=(60, 150, 90))
    return img


def clear():
    removed = 0
    for item in db.list_items(status=None):
        if item["image"].startswith("demo_"):
            for name in (item["image"], item["thumb"]):
                path = os.path.join(UPLOAD_DIR, name)
                if os.path.exists(path):
                    os.remove(path)
            db.delete_item(item["id"])
            removed += 1
    print(f"Removed {removed} demo item(s).")


def main():
    db.init()
    if "--clear" in sys.argv:
        clear()
        return

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    existing = {i["image"] for i in db.list_items(status=None)}

    for spec in DEMO:
        image = f"{spec['stem']}.jpg"
        if image in existing:
            continue
        thumb = f"{spec['stem']}_t.jpg"
        img = draw(spec["shape"], spec["bg"], spec["fg"])
        img.save(os.path.join(UPLOAD_DIR, image), "JPEG", quality=88)
        t = img.copy()
        t.thumbnail((600, 600))
        t.save(os.path.join(UPLOAD_DIR, thumb), "JPEG", quality=80)

        db.add_item(
            image=image, thumb=thumb, campus="durham",
            title=spec["title"], category=spec["category"], color=spec["color"],
            brand=spec["brand"], ai_description=spec["ai_description"],
            user_note=spec["note"], tags=spec["tags"],
            search_text=" ".join(filter(None, [
                spec["title"], spec["category"], spec["color"], spec["brand"] or "",
                spec["ai_description"], spec["note"] or "", " ".join(spec["tags"]),
            ])).lower(),
            found_location=spec["location"], found_at=spec["found_at"],
            finder_name=spec["finder_name"], finder_contact=spec["finder_contact"],
        )
        print(f"  + {spec['title']}")

    print(f"\nDone. {db.counts()['unclaimed']} unclaimed item(s) in the database.")


if __name__ == "__main__":
    main()
