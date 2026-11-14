"""Stage 2: one dark atmospheric image per section. Cached on disk."""
import time
import urllib.parse
from pathlib import Path

import requests


def generate(script, cfg, outdir: Path, dry=False):
    outdir.mkdir(parents=True, exist_ok=True)
    w, h = cfg["video"]["width"], cfg["video"]["height"]
    paths = []
    for i, sec in enumerate(script["sections"]):
        p = outdir / f"section_{i:02d}.jpg"
        paths.append(p)
        if p.exists() and p.stat().st_size > 5000:
            continue  # cache
        if dry:
            _placeholder(p, w, h, i)
            continue
        prompt = f"{sec['image_prompt']}. {cfg['images']['style_suffix']}"
        # render a bit larger than the frame so Ken Burns has room to move
        url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
               + f"?width={int(w * 1.25)}&height={int(h * 1.25)}&nologo=true&seed={2000 + i}")
        r = None
        for attempt in range(cfg["images"]["retries"]):
            try:
                r = requests.get(url, timeout=180)
            except requests.RequestException:
                time.sleep(8 * (attempt + 1))
                continue
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                p.write_bytes(r.content)
                break
            time.sleep(8 * (attempt + 1))
        else:
            raise RuntimeError(f"image failed for section {i}: {getattr(r, 'status_code', 'network error')}")
        time.sleep(2)  # be gentle with the free service
    return paths


def _placeholder(p, w, h, i):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (int(w * 1.25), int(h * 1.25)), (20 + i * 8, 25, 40))
    ImageDraw.Draw(img).text((50, 50), f"section {i + 1}", fill="white")
    img.save(p, quality=85)
