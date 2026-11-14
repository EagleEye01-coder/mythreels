"""Stage 2: one image per scene (shared across languages). Cached on disk."""
import time
import urllib.parse
from pathlib import Path

import requests


def generate(script, cfg, outdir: Path, dry=False):
    outdir.mkdir(parents=True, exist_ok=True)
    chars = "; ".join(f"{k}: {v}" for k, v in script["characters"].items())
    w, h = cfg["video"]["width"], cfg["video"]["height"]
    paths = []
    for i, scene in enumerate(script["scenes"]):
        p = outdir / f"scene_{i:02d}.jpg"
        paths.append(p)
        if p.exists() and p.stat().st_size > 5000:
            continue  # cache
        if dry:
            _placeholder(p, w, h, i)
            continue
        prompt = f"{scene['image_prompt']}. Characters: {chars}. {cfg['images']['style_suffix']}"
        # render a bit larger than the frame so Ken Burns has room to move
        url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
               + f"?width={int(w * 1.25)}&height={int(h * 1.25)}&nologo=true&seed={1000 + i}")
        for attempt in range(cfg["images"]["retries"]):
            r = requests.get(url, timeout=180)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                p.write_bytes(r.content)
                break
            time.sleep(8 * (attempt + 1))
        else:
            raise RuntimeError(f"image failed for scene {i}: {r.status_code}")
        time.sleep(2)  # be gentle with the free service
    return paths


def _placeholder(p, w, h, i):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (int(w * 1.25), int(h * 1.25)),
                    ((40 + i * 15) % 255, (90 + i * 10) % 255, 160))
    ImageDraw.Draw(img).text((50, 50), f"scene {i + 1}", fill="white")
    img.save(p, quality=85)
