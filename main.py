"""Orchestrator. Usage:
    python main.py --dry                 # no network, stub script/images/audio/upload
    python main.py --no-upload           # real generation, skip upload
    python main.py                       # full run
    python main.py --topic ganesha-race  # force a topic
"""
import argparse
import json
from pathlib import Path

import yaml

from pipeline import images, render, script_gen, tts, upload

ROOT = Path(__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--topic")
    ap.add_argument("--langs", default="en,hi")
    a = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    topics_path = ROOT / "topics.yaml"
    topics = yaml.safe_load(topics_path.read_text())["topics"]
    todo = [t for t in topics if (t["id"] == a.topic if a.topic else t["status"] == "todo")]
    if not todo:
        print("No topics left. Add more to topics.yaml.")
        return
    topic = todo[0]
    work = ROOT / "work" / topic["id"]
    out = ROOT / "output" / topic["id"]
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    print(f"Topic: {topic['title']}")

    sp = work / "script.json"
    if sp.exists():
        script = json.loads(sp.read_text())
    else:
        script = script_gen.generate(topic, cfg, dry=a.dry)
        sp.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

    imgs = images.generate(script, cfg, work / "img", dry=a.dry)
    music = ROOT / "assets" / "music.mp3"

    results = {}
    for lang in a.langs.split(","):
        auds, durs = tts.generate(script, lang, cfg, work / "audio", dry=a.dry)
        mp4 = out / f"{topic['id']}_{lang}.mp4"
        render.render(script, lang, imgs, auds, durs, cfg, work / "tmp", music, mp4)
        print(f"Rendered {mp4} ({sum(durs):.0f}s narration)")
        if not a.no_upload:
            title = script["title"][lang]
            vid = upload.upload(mp4, title, script["description"][lang], cfg, lang, dry=a.dry)
            results[lang] = vid
            print(f"Uploaded {lang}: {vid} (private - approve in YouTube Studio)")

    if results and not a.dry:
        for t in topics:
            if t["id"] == topic["id"]:
                t["status"] = "done"
        topics_path.write_text(yaml.safe_dump({"topics": topics}, sort_keys=False,
                                              allow_unicode=True))
    (out / "result.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
