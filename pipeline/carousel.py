"""Render carousel slides: cream paper, bold left-aligned text, one illustration band."""
import hashlib
import io
import os
import subprocess
import time
import urllib.parse

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont


def _font_path():
    for query in ("Noto Sans:bold", "Open Sans:bold", "DejaVu Sans:bold"):
        try:
            p = subprocess.run(["fc-match", "-f", "%{file}", query],
                               capture_output=True, text=True, timeout=10).stdout.strip()
            if p and os.path.exists(p):
                return p
        except Exception:
            pass
    return "DejaVuSans-Bold.ttf"


FONT = _font_path()
CROP = 80  # extra pixels requested at the bottom of generated art, then cropped off


def paper(w, h, base):
    rng = np.random.default_rng(7)
    img = np.ones((h, w, 3), np.float32) * np.array(base, np.float32)
    grain = rng.normal(0, 2.2, (h, w, 1)).astype(np.float32)
    blotch = Image.fromarray((rng.random((h // 40, w // 40)) * 255).astype(np.uint8))
    blotch = np.asarray(blotch.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(30)),
                        np.float32)[..., None]
    img += grain + (blotch - 128) / 128 * 4
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    img *= (1 - 0.06 * np.clip(d - 0.6, 0, 1))[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def _fallback_art(w, h, seed):
    """Soft watercolor wash band used when image generation is unavailable."""
    rng = np.random.default_rng(seed)
    art = Image.new("RGB", (w, h), (250, 244, 228))
    d = ImageDraw.Draw(art, "RGBA")
    for _ in range(14):
        cx, cy = rng.integers(0, w), rng.integers(h // 3, h)
        r = rng.integers(80, 260)
        col = [(210, 130, 120), (140, 160, 120), (120, 140, 170), (200, 170, 110)][rng.integers(0, 4)]
        d.ellipse([cx - r, cy - r // 2, cx + r, cy + r // 2], fill=(*col, 38))
    return art.filter(ImageFilter.GaussianBlur(14))


def illustration(prompt, cfg, workdir, dry=False):
    w, h = cfg["slide"]["width"], cfg["illustration"]["height"]
    key = hashlib.md5(f"v2{prompt}{w}{h}".encode()).hexdigest()[:10]
    cache = os.path.join(workdir, f"art_{key}.png")
    if os.path.exists(cache):
        return Image.open(cache).convert("RGB")
    seed = int(key, 16) % 10_000
    if not dry:
        full = f"{prompt}, {cfg['illustration']['style']}"
        url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(full)
               + f"?width={w}&height={h + CROP}&nologo=true&seed={seed}")
        for i in range(cfg["illustration"]["retries"]):
            try:
                r = requests.get(url, timeout=120)
                if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                    art = Image.open(io.BytesIO(r.content)).convert("RGB")
                    # drop the bottom strip: the free tier stamps a watermark there
                    art = art.crop((0, 0, art.width, art.height - int(art.height * CROP / (h + CROP))))
                    art = art.resize((w, h))
                    art.save(cache)
                    return art
                print(f"::warning::illustration HTTP {r.status_code} (try {i + 1})")
            except Exception as e:
                print(f"::warning::illustration error {e} (try {i + 1})")
            time.sleep(6 * (i + 1))
        print("::warning::using fallback wash instead of an illustration")
    art = _fallback_art(w, h, seed)
    art.save(cache)
    return art


def _wrap(draw, text, font, max_w):
    lines = []
    for para in text.split("\n"):
        if not para.strip():
            lines.append("")
            continue
        cur = ""
        for word in para.split():
            test = f"{cur} {word}".strip()
            if draw.textlength(test, font=font) <= max_w:
                cur = test
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def _fit(draw, blocks, cfg):
    """blocks: list of (text, colour). Largest font size whose total height fits."""
    s = cfg["slide"]
    max_w = s["width"] - 2 * s["margin_x"]
    avail = s["text_bottom"] - s["text_top"]
    for size in range(s["font_max"], s["font_min"] - 1, -2):
        font = ImageFont.truetype(FONT, size)
        lh = int(size * s["line_spacing"])
        laid = [(_wrap(draw, t, font, max_w), c) for t, c in blocks]
        total = sum(len(ls) for ls, _ in laid) * lh
        if total <= avail:
            return font, lh, laid, size
    font = ImageFont.truetype(FONT, s["font_min"])
    lh = int(s["font_min"] * s["line_spacing"])
    return font, lh, [(_wrap(draw, t, font, max_w), c) for t, c in blocks], s["font_min"]


HEART = "{heart}"  # marker in text; drawn as a shape so it needs no font glyph


def _heart(d, x, y, size, col):
    r = size / 4
    d.ellipse([x, y, x + 2 * r, y + 2 * r], fill=col)
    d.ellipse([x + 2 * r, y, x + 4 * r, y + 2 * r], fill=col)
    d.polygon([(x + 0.06 * r, y + 1.35 * r), (x + 3.94 * r, y + 1.35 * r), (x + 2 * r, y + 3.6 * r)], fill=col)


def render_slide(blocks, art, cfg):
    s = cfg["slide"]
    img = paper(s["width"], s["height"], s["paper"])
    # feathered illustration band at the bottom
    ah = art.size[1]
    mask = Image.linear_gradient("L").resize((s["width"], ah))  # 0 top -> 255 bottom
    mask = mask.point(lambda v: min(255, int(v * 3.2)))
    img.paste(art, (0, s["height"] - ah), mask)
    d = ImageDraw.Draw(img)
    font, lh, laid, size = _fit(d, blocks, cfg)
    y = s["text_top"]  # top-aligned, like the reference account
    for lines, col in laid:
        for ln in lines:
            if ln.endswith(HEART):
                base = ln[: -len(HEART)].rstrip()
                d.text((s["margin_x"], y), base, font=font, fill=tuple(col))
                hx = s["margin_x"] + d.textlength(base + " ", font=font)
                _heart(d, hx, y + size * 0.24, size * 0.70, (214, 40, 52))
            elif ln:
                d.text((s["margin_x"], y), ln, font=font, fill=tuple(col))
            y += lh
    return img, size


def render_all(story, slides, cfg, outdir, workdir, dry=False):
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(workdir, exist_ok=True)
    s = cfg["slides"]
    ink, accent = cfg["slide"]["ink"], cfg["slide"]["accent"]
    art = illustration(story["illustration"], cfg, workdir, dry)
    pages = []
    # cover
    cover = [(story["title"], accent)]
    if story.get("hook"):
        cover.append(("\n" + story["hook"], ink))
    cover.append(("\n" + s["cover_cta"], accent))
    pages.append(cover)
    for text in slides:
        pages.append([(text, ink)])
    pages.append([(s["closing"], ink)])
    sizes = []
    for i, blocks in enumerate(pages, 1):
        img, size = render_slide(blocks, art, cfg)
        img.save(os.path.join(outdir, f"slide_{i:02d}.png"), optimize=True)
        sizes.append(size)
    return len(pages), sizes
