"""Expand the user's real moment (`idea`) into carousel slide text with Gemini."""
import json
import os
import re

import requests

PROMPT = """You help a parent write a short, honest first-person story carousel for Instagram.
The author's real moment, in their own words:
\"\"\"{idea}\"\"\"

Write {n} slides of body text that tell this story in order, using ONLY what the author said.
Do not invent events, names, numbers or quotes the author did not give. If a detail is missing,
stay general instead of making it up.

Style: first person, plain simple English, calm and vulnerable, one beat per slide,
25-55 words per slide, short sentences. Use \\n\\n for a paragraph break inside a slide.
End the body with the lesson or decision, not with a sales line.

Also give:
- "caption": one-line hook caption (e.g. an honest admission), then 2 short lines.
Return STRICT JSON: {{"slides": ["..."], "caption": "..."}}"""


def _call(model, key, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = requests.post(
        url,
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7},
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def draft(idea, cfg, dry=False):
    n = max(4, cfg["slides"]["target_count"] - 2)
    if dry or not os.environ.get("GEMINI_API_KEY"):
        if not dry:
            print("::warning::GEMINI_API_KEY missing; using stub slides")
        body = [
            "A friend told me something recently.\n\nIt should have stayed a passing remark.",
            "But it lingered in my head for days.\n\nI started doubting a choice I was sure about.",
            "So I sat down with my wife and we talked honestly.\n\nNot about what looked good. About what we felt.",
            "The more we talked, the clearer it got.",
            "The pull was coming from my pride, not from his needs.",
            "We stayed with what suits him.",
        ]
        return body, "This wasn't easy for me to admit.\n\nSave this if it feels familiar."
    key = os.environ["GEMINI_API_KEY"]
    last = None
    for model in cfg["gemini"]["models"]:
        try:
            raw = _call(model, key, PROMPT.format(idea=idea.strip(), n=n))
            raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
            data = json.loads(raw)
            slides = [s.strip() for s in data["slides"] if s.strip()]
            if len(slides) >= 3:
                print(f"drafted {len(slides)} slides with {model}")
                return slides, data.get("caption", "").strip()
        except Exception as e:  # try next model
            last = f"{model}: {e}"
            print(f"::warning::draft failed ({last})")
    raise RuntimeError(f"All Gemini models failed. Last: {last}")
