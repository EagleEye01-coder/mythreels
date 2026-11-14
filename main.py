"""Orchestrator. Usage:
    python main.py --dry                 # no network: stub script/images/voice/upload
    python main.py --no-upload           # real generation, skip upload
    python main.py                       # full run (uploads PRIVATE to YouTube)
    python main.py --topic haveli-lamp   # force a topic
"""
import argparse
import json
import shutil
from pathlib import Path

import yaml

from pipeline import images, render, script_gen, tts, upload

ROOT = Path(__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--topic")
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
        script = json.loads(sp.read_text(encoding="utf-8"))
    else:
        script = script_gen.generate(topic, cfg, dry=a.dry)
        sp.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

    imgs = images.generate(script, cfg, work / "img", dry=a.dry)
    narration, timeline, section_durs = tts.generate(script, cfg, work / "audio", dry=a.dry)
    print(f"Narration: {sum(section_durs) / 60:.1f} min, {len(timeline)} sentences")

    mp4 = out / f"{topic['id']}.mp4"
    _, mix = render.render(script, imgs, narration, timeline, section_durs, cfg, work / "tmp", mp4)
    shutil.copy(mix, out / f"{topic['id']}_audio.wav")  # input for the podcast MP3 (phase 2)
    print(f"Rendered {mp4}")

    result = {}
    if not a.no_upload:
        vid = upload.upload(mp4, script["title"], script["description"], cfg,
                            cfg["language"]["code"], dry=a.dry)
        result["youtube"] = vid
        print(f"Uploaded: {vid} (private - approve in YouTube Studio)")
        if not a.dry:
            for t in topics:
                if t["id"] == topic["id"]:
                    t["status"] = "done"
            topics_path.write_text(yaml.safe_dump({"topics": topics}, sort_keys=False, allow_unicode=True),
                                   encoding="utf-8")
    (out / "result.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
