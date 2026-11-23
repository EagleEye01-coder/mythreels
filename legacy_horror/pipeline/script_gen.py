"""Stage 1: Hindi horror script via Gemini (free tier).
One call for the outline, then one call per section (keeps length on target, avoids truncation).
"""
import json
import os
import re
import time

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEV = re.compile(r"[ऀ-ॿ]")
LAT = re.compile(r"[A-Za-z]")

OUTLINE_PROMPT = """You write slow-burn Indian horror audio stories for a podcast.
Premise: {premise}
Setting: {setting}

Write an ORIGINAL story outline. Rules:
- Atmospheric, psychological, folk-horror feel. Dread over gore.
- Absolutely no graphic violence, blood or gore, no sexual content, no real people, real crimes or real tragedies, no mockery of any religion or community.
- First-person narrator, an ordinary person, with believable details of everyday Indian life.
- Exactly {n} sections: a hook, middle sections that escalate, a climax, and a final unsettling ending that is not fully explained.
- image_prompt: English, one dark atmospheric scene for that section. No close-up faces, no text, no gore.
Return ONLY JSON:
{{"title_hi": "catchy Hindi title in Devanagari", "description_hi": "2-3 lines in Hindi, no spoilers", "sections": [{{"beat": "what happens in this section (English)", "image_prompt": "..."}}]}}"""

SECTION_PROMPT = """You are writing section {i} of {n} of a Hindi horror audio story, to be read aloud by one narrator.
Premise: {premise}
Setting: {setting}

Outline (English):
{outline}

Story so far (Hindi, last part):
{so_far}

Write ONLY section {i}. What happens: {beat}
Rules:
- Natural spoken Hindi in Devanagari script. No English words in Latin script. Write numbers and times in Hindi words.
- About {words} words. Short sentences. Every sentence ends with । or ? or !
- Paragraphs separated by a blank line; start a new paragraph at each tense beat.
- Slow-burn dread, sensory detail. No gore, no graphic violence.
- {extra}
- Output ONLY the story text: no headings, no section numbers, no notes."""


def _call(prompt, cfg, as_json=False, temperature=0.9):
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}
    gen = {"temperature": temperature}
    if as_json:
        gen["responseMimeType"] = "application/json"
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen}
    errors = []
    for model in cfg["llm"]["models"]:
        for attempt in range(2):
            try:
                r = requests.post(API.format(model=model), json=body, headers=headers, timeout=180)
            except requests.RequestException as e:
                errors.append(f"{model}: network error {type(e).__name__}")
                time.sleep(5)
                continue
            if r.status_code == 200:
                try:
                    parts = r.json()["candidates"][0]["content"]["parts"]
                    return "".join(p.get("text", "") for p in parts)
                except (KeyError, IndexError):
                    errors.append(f"{model}: empty response")
                    break
            errors.append(f"{model}: HTTP {r.status_code} {r.text[:200]}")
            if r.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                time.sleep(20)
                continue
            break
    raise RuntimeError("Gemini failed on all models:\n" + "\n".join(errors))


def _hindi_ok(text):
    dev, lat = len(DEV.findall(text)), len(LAT.findall(text))
    return dev > 0 and dev / (dev + lat) >= 0.9


def _outline(topic, cfg):
    n = cfg["story"]["sections"]
    prompt = OUTLINE_PROMPT.format(premise=topic["premise"], setting=topic["setting"], n=n)
    last = None
    for _ in range(3):
        txt = _call(prompt, cfg, as_json=True, temperature=0.8)
        try:
            d = json.loads(re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip())
            assert len(d["sections"]) == n and d["title_hi"] and d["description_hi"]
            assert all(s["beat"] and s["image_prompt"] for s in d["sections"])
            return d
        except Exception as e:
            last = e
    raise RuntimeError(f"outline failed: {last}")


def _section(topic, outline, i, so_far, cfg):
    n, words = cfg["story"]["sections"], cfg["story"]["section_words"]
    if i == 1:
        extra = "Open with a gripping first line that makes the listener lean in."
    elif i == n:
        extra = "End on an unsettling final image or line. Do not explain everything."
    else:
        extra = "Continue seamlessly from the story so far. Do not repeat or summarise it."
    outline_txt = "\n".join(f"{k + 1}. {s['beat']}" for k, s in enumerate(outline["sections"]))
    prompt = SECTION_PROMPT.format(
        i=i, n=n, premise=topic["premise"], setting=topic["setting"], outline=outline_txt,
        so_far=so_far[-1500:] or "(this is the beginning)", beat=outline["sections"][i - 1]["beat"],
        words=words, extra=extra)
    last = ""
    for _ in range(3):
        text = _call(prompt, cfg).strip()
        wc = len(text.split())
        if _hindi_ok(text) and words * 0.5 <= wc <= words * 2.2:
            return text
        last = f"{wc} words, hindi_ok={_hindi_ok(text)}"
    raise RuntimeError(f"section {i} failed quality checks ({last})")


def generate(topic, cfg, dry=False):
    if dry:
        return _stub(topic, cfg["story"]["sections"])
    outline = _outline(topic, cfg)
    narrations = []
    for i in range(1, cfg["story"]["sections"] + 1):
        narrations.append(_section(topic, outline, i, "\n\n".join(narrations), cfg))
        print(f"  section {i}: {len(narrations[-1].split())} words")
    return {
        "title": outline["title_hi"],
        "description": outline["description_hi"],
        "sections": [{"image_prompt": s["image_prompt"], "narration": t}
                     for s, t in zip(outline["sections"], narrations)],
    }


def _stub(topic, n):
    para = "रात बहुत गहरी थी। हवा रुक गई थी। मैंने दरवाज़े की ओर देखा... वहाँ कोई नहीं था!\n\nफिर वही आवाज़ आई। धीमी, बहुत धीमी।"
    return {
        "title": topic["title"],
        "description": "Stub description.",
        "sections": [{"image_prompt": f"dark foggy scene {i + 1}, an old building at night",
                      "narration": para} for i in range(n)],
    }
