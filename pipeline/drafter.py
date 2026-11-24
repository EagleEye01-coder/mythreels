"""Expand the user's real moment (`idea`) into carousel slide text with Gemini."""
import json
import os
import re

import requests

PROMPT = """You are a gifted writer of first-person parenting reflections for Instagram carousels
(warm, honest, specific, the kind people save and send to their spouse).
The author gave this seed anecdote:
\"\"\"{idea}\"\"\"

Narrator: {author}. Write every slide in his first-person voice. His spouse is "my wife",
never "my husband". Never write the narrator as a woman or a mother.

Turn it into a complete, engaging story told across {n} slides of body text.
Build it out: you MAY add small, believable scenes, sensory details, the child's actions,
inner thoughts, and a quiet conversation between the parents, as long as they fit the seed.
Keep everything low-stakes and ordinary. Do NOT add medical, legal or financial claims, brand or
school names, real public figures, statistics, or anything that blames or exposes a real person.
Keep the names and facts the author gave exactly as given.

Structure:
1. Open in a concrete moment (a scene, not a summary).
2. Show what we noticed about the child, with small vivid details.
3. Let the worry grow; admit something a little uncomfortable.
4. A turning point (a realisation or a talk with the spouse).
5. The lesson, stated simply and warmly.
6. Last body slide: a question that invites the reader to comment.

Style: first person, simple spoken English, warm and vulnerable. 40-70 words per slide, 3-5
sentences, varied sentence length. Each slide ends on a thought that makes the reader swipe.
Use \\n\\n for a paragraph break inside a slide. No hashtags, no emojis, no sales language.

Also give "caption": a one-line honest hook, then 2 short lines, no hashtags.
Return STRICT JSON: {{"slides": ["..."], "caption": "..."}}"""


def _call(model, key, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = requests.post(
        url,
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
        },
        timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


_SKIP = ("image", "tts", "audio", "live", "embed", "vision", "robotics", "computer", "learnlm", "gemma", "aqa")


def _discover(key):
    """Flash-class text models this key can call, newest first (stable before preview, full before lite)."""
    try:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                         headers={"x-goog-api-key": key}, timeout=30)
        r.raise_for_status()
        found = []
        for m in r.json().get("models", []):
            name = m["name"].split("/")[-1]
            if ("generateContent" in m.get("supportedGenerationMethods", [])
                    and "flash" in name and not any(s in name for s in _SKIP)):
                v = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
                found.append((float(v.group(1)) if v else 0.0, "lite" not in name,
                              not re.search(r"preview|exp", name), name))
        found.sort(reverse=True)
        names = [f[3] for f in found]
        print(f"models available: {', '.join(names) or 'none'}")
        return names
    except Exception as e:
        print(f"::warning::model discovery failed ({e}); using config list")
        return []


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
    models = _discover(key)[:5]
    models += [m for m in cfg["gemini"]["models"] if m not in models]
    for model in models:
        try:
            raw = _call(model, key, PROMPT.format(idea=idea.strip(), n=n, author=cfg.get("author", "a parent")))
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
