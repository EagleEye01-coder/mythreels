"""Stage 1: story script via Gemini (free tier). One call returns both languages."""
import json
import os
import time

import requests

SYSTEM = """You write short educational animated stories for children aged 4-9, based on Indian mythology.
Rules:
- Use the widely known version of the story. Do not invent myths. Keep it gentle, non-violent, non-sectarian, respectful.
- Total narration about {seconds} seconds when read aloud, split into exactly {scenes} scenes.
- Scene narration: 2 short sentences max, simple words, warm tone.
- Last scene states the moral for kids.
- image_prompt: English, visual description of the scene only. Always describe characters using the SAME fixed descriptions from "characters" so they look consistent.
- Output ONLY valid JSON matching the schema."""

SCHEMA_HINT = """{
 "title": {"en": "...", "hi": "..."},
 "description": {"en": "2-3 lines", "hi": "2-3 lines"},
 "characters": {"Name": "fixed visual description: age, skin tone, clothes, colors, distinguishing features"},
 "moral": {"en": "...", "hi": "..."},
 "scenes": [{"image_prompt": "...", "narration": {"en": "...", "hi": "..."}}]
}"""


def generate(topic, cfg, dry=False):
    n = cfg["video"]["scenes"]
    if dry:
        return _stub(topic, n)
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}
    prompt = (SYSTEM.format(seconds=cfg["video"]["target_seconds"], scenes=n)
              + f"\n\nStory: {topic['title']} (source: {topic['source']})\n\nSchema:\n{SCHEMA_HINT}")
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}}
    errors = []
    for model in cfg["llm"]["models"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(2):
            try:
                r = requests.post(url, json=body, headers=headers, timeout=120)
            except requests.RequestException as e:
                errors.append(f"{model}: network error {type(e).__name__}")
                time.sleep(5)
                continue
            if r.status_code == 200:
                try:
                    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    data = json.loads(text)
                    _validate(data, n, cfg)
                    print(f"Script generated with {model}")
                    return data
                except Exception as e:  # bad JSON / wrong scene count: retry once, then next model
                    errors.append(f"{model}: bad output ({type(e).__name__}: {str(e)[:120]})")
                    continue
            errors.append(f"{model}: HTTP {r.status_code} {r.text[:200]}")
            if r.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                time.sleep(20)  # transient / rate limit: wait, retry same model once
                continue
            break  # 400/403/404 etc: model unavailable, try next
    raise RuntimeError("Gemini failed on all models:\n" + "\n".join(errors))


def _validate(d, n, cfg):
    assert len(d["scenes"]) == n, f"expected {n} scenes, got {len(d['scenes'])}"
    for lang in cfg["languages"]:
        assert d["title"][lang] and d["description"][lang]
        for s in d["scenes"]:
            assert s["narration"][lang].strip() and s["image_prompt"].strip()


def _stub(topic, n):
    return {
        "title": {"en": topic["title"], "hi": topic["title"]},
        "description": {"en": "Stub description.", "hi": "Stub description."},
        "characters": {"Hero": "a small boy with golden skin, orange clothes"},
        "moral": {"en": "Be kind.", "hi": "Be kind."},
        "scenes": [{"image_prompt": f"scene {i + 1}, a small boy in a green forest",
                    "narration": {"en": f"This is scene number {i + 1} of the story.",
                                  "hi": f"This is scene number {i + 1} of the story."}}
                   for i in range(n)],
    }
