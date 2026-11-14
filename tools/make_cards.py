"""Generate the cover cards for the seeded Library into seed/covers/.

Run from the project folder:  python tools/make_cards.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from covers import make_cover  # noqa: E402
from seed_data import COURSE, DOWNLOADS, GUIDES, download_slug  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed")


def main():
    for g in GUIDES:
        make_cover(os.path.join(OUT, g["slug"] + ".jpg"), g["title"], f"The Atelier Series · No. {g['no']}",
                   g["subtitle"], "ebook")
        if g["video"]:
            make_cover(os.path.join(OUT, g["slug"] + "-video.jpg"), g["title"], f"Video guide · No. {g['no']}",
                       "", "class")
    make_cover(os.path.join(OUT, COURSE["slug"] + ".jpg"), COURSE["title"], "Course · Three modules",
               "For estate agents, real estate agents and brokers", "course")
    for no, title, desc, _ in DOWNLOADS:
        make_cover(os.path.join(OUT, download_slug(no, title) + ".jpg"), title, "Real Estate Agents course · Tool",
                   desc, "template", number=no)
    from seed_data import SCHOOL_VIDEOS
    for v in SCHOOL_VIDEOS:
        make_cover(os.path.join(OUT, v["slug"] + ".jpg"), v["title"], v["eyebrow"], v["subtitle"], "class")
    print("Covers written to", OUT)


if __name__ == "__main__":
    main()
