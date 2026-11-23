"""Story carousel generator.

python main.py              # first story with status: todo
python main.py --story ID   # a specific story
python main.py --dry        # offline test: stub text, no network
"""
import argparse
import json
import os
import shutil
import sys
import zipfile

import yaml

from pipeline import carousel, drafter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--story", default="")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    cfg = yaml.safe_load(open("config.yaml"))
    stories = yaml.safe_load(open("stories.yaml"))["stories"]
    pick = [s for s in stories if (s["id"] == a.story if a.story else s.get("status") == "todo")]
    if not pick:
        print("No matching story (set status: todo or pass --story ID)")
        return 1
    story = pick[0]
    sid = story["id"]
    out, work = os.path.join("output", sid), os.path.join("work", sid)
    shutil.rmtree(out, ignore_errors=True)

    slides = [s for s in (story.get("slides") or []) if str(s).strip()]
    caption = (story.get("caption") or "").strip()
    drafted = False
    if not slides:
        idea = (story.get("idea") or "").strip()
        if not idea:
            print("::error::story needs either `slides` or an `idea`")
            return 1
        slides, dcap = drafter.draft(idea, cfg, dry=a.dry)
        caption = caption or dcap
        drafted = True

    n, sizes = carousel.render_all(story, slides, cfg, out, work, dry=a.dry)

    tags = (story.get("hashtags") or "").strip()
    with open(os.path.join(out, "caption.txt"), "w") as f:
        f.write(f"{caption}\n\n{tags}\n".strip() + "\n")
    # Drafted text is saved so you can paste it into stories.yaml, edit, and re-run.
    with open(os.path.join(out, "slides_text.yaml"), "w") as f:
        yaml.safe_dump({"slides": slides}, f, allow_unicode=True, sort_keys=False, width=100)
    json.dump({"id": sid, "slides": n, "font_sizes": sizes, "drafted_by_ai": drafted},
              open(os.path.join(out, "result.json"), "w"), indent=2)
    with zipfile.ZipFile(os.path.join(out, f"{sid}.zip"), "w") as z:
        for fn in sorted(os.listdir(out)):
            if fn.endswith((".png", ".txt")):
                z.write(os.path.join(out, fn), fn)
    if drafted:
        print("::notice::Slide text was AI-drafted from your idea. Review slides_text.yaml before posting.")
    print(f"done: {n} slides -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
