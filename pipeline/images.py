"""Stage 2: one dark atmospheric image per section. Cached on disk.

The free image service is flaky, so: retry with growing waits and smaller sizes,
and if it still fails use a generated dark fog frame so the run never dies.
Fallback frames are saved separately, so a re-run tries the real image again.
"""
import time
import urllib.parse
from pathlib import Path

import requests


def generate(script, cfg, outdir: Path, dry=False):
    outdir.mkdir(parents=True, exist_ok=True)
    w, h = cfg["video"]["width"], cfg["video"]["height"]
    paths, fallbacks = [], []
    for i, sec in enumerate(script["sections"]):
        p = outdir / f"section_{i:02d}.jpg"
        fb = outdir / f"section_{i:02d}.fallback.jpg"
        if p.exists() and p.stat().st_size > 5000:
            paths.append(p)  # cache
            continue
        if dry:
            _placeholder(p, w, h, i)
            paths.append(p)
            continue
        if _fetch(sec["image_prompt"], cfg, i, p):
            paths.append(p)
            time.sleep(2)  # be gentle with the free service
        else:
            _fog(fb, w, h, i)
            paths.append(fb)
            fallbacks.append(i + 1)
            print(f"::warning::image for section {i + 1} failed, using a fog fallback frame")
    if fallbacks:
        print(f"Fallback frames used for sections: {fallbacks} (re-run to retry them)")
    return paths


def _fetch(prompt_text, cfg, i, path: Path) -> bool:
    w, h = cfg["video"]["width"], cfg["video"]["height"]
    prompt = f"{prompt_text}. {cfg['images']['style_suffix']}"
    tries = cfg["images"]["retries"]
    for attempt in range(tries):
        scale = 1.25 if attempt < 3 else 1.0  # smaller image on later attempts
        url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
               + f"?width={int(w * scale)}&height={int(h * scale)}&nologo=true&seed={2000 + i + attempt}")
        try:
            r = requests.get(url, timeout=180)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image") \
                    and len(r.content) > 5000:
                path.write_bytes(r.content)
                return True
            print(f"  section {i + 1} image attempt {attempt + 1}/{tries}: HTTP {r.status_code}")
        except requests.RequestException as e:
            print(f"  section {i + 1} image attempt {attempt + 1}/{tries}: {type(e).__name__}")
        time.sleep(min(10 * (attempt + 1), 60))
    return False


def _fog(p, w, h, i):
    """Dark, blurry fog texture: a usable frame when the image service is down."""
    from PIL import Image, ImageFilter, ImageOps
    W, H = int(w * 1.25), int(h * 1.25)
    noise = Image.effect_noise((W // 4, H // 4), 70 + 5 * i).filter(ImageFilter.GaussianBlur(18))
    img = ImageOps.colorize(ImageOps.autocontrast(noise), black="#04060b", white="#2b3445")
    img.resize((W, H), Image.BICUBIC).save(p, quality=88)


def _placeholder(p, w, h, i):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (int(w * 1.25), int(h * 1.25)), (20 + i * 8, 25, 40))
    ImageDraw.Draw(img).text((50, 50), f"section {i + 1}", fill="white")
    img.save(p, quality=85)
