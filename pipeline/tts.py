"""Stage 3: narration via edge-tts (free), one clip per sentence, assembled with exact silences.

Returns the narration wav, a caption timeline (exact, no drift) and per-section durations.
Pure-Python wav assembly so timings are sample-accurate.
"""
import asyncio
import re
import subprocess
import wave
from pathlib import Path

SR = 24000


def split_sentences(text, cfg):
    """-> list of (sentence, pause_seconds_after)."""
    s = cfg["story"]
    out = []
    for para in re.split(r"\n\s*\n", text.strip()):
        sents = [x.strip() for x in re.split(r"(?<=[।!?.])\s+", para.replace("\n", " ").strip()) if x.strip()]
        for k, sent in enumerate(sents):
            pause = s["pause_paragraph"] if k == len(sents) - 1 else s["pause_sentence"]
            if sent.endswith(("…", "...")):
                pause = max(pause, s["pause_ellipsis"])
            out.append((sent, pause))
    return out


async def _synth(text, lang_cfg, path):
    import edge_tts
    await edge_tts.Communicate(text, lang_cfg["voice"], rate=lang_cfg["rate"],
                               pitch=lang_cfg["pitch"]).save(str(path))


async def _synth_all(jobs, lang_cfg):
    sem = asyncio.Semaphore(3)

    async def one(text, path):
        async with sem:
            for attempt in range(4):
                try:
                    await _synth(text, lang_cfg, path)
                    if path.exists() and path.stat().st_size > 500:
                        return
                except Exception:
                    pass
                await asyncio.sleep(3 * (attempt + 1))
            raise RuntimeError(f"TTS failed for: {text[:40]}")

    await asyncio.gather(*(one(t, p) for t, p in jobs))


def _read_wav(path):
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes())


def generate(script, cfg, outdir: Path, dry=False):
    outdir.mkdir(parents=True, exist_ok=True)
    lang_cfg = cfg["language"]
    items = []  # (section_idx, sentence, pause, wav_path)
    jobs = []
    for si, sec in enumerate(script["sections"]):
        for k, (sent, pause) in enumerate(split_sentences(sec["narration"], cfg)):
            mp3 = outdir / f"s{si:02d}_{k:03d}.mp3"
            wav = outdir / f"s{si:02d}_{k:03d}.wav"
            items.append((si, sent, pause, mp3, wav))
            if not wav.exists():
                jobs.append((sent, mp3))

    if jobs and not dry:
        asyncio.run(_synth_all([j for j in jobs if not j[1].exists()], lang_cfg))
    for si, sent, pause, mp3, wav in items:
        if wav.exists():
            continue
        if dry:  # silent stand-in, length ~ text length
            with wave.open(str(wav), "wb") as w:
                w.setparams((1, 2, SR, 0, "NONE", "not compressed"))
                w.writeframes(b"\x00\x00" * int(SR * max(1.0, len(sent) / 14)))
        else:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ar", str(SR),
                            "-ac", "1", "-f", "wav", str(wav)], check=True)

    narration = outdir / "narration.wav"
    timeline, section_durs = [], [0.0] * len(script["sections"])
    pos = 0  # frames
    with wave.open(str(narration), "wb") as out:
        out.setparams((1, 2, SR, 0, "NONE", "not compressed"))
        for si, sent, pause, mp3, wav in items:
            frames = _read_wav(wav)
            n = len(frames) // 2
            gap = int(pause * SR)
            out.writeframes(frames)
            out.writeframes(b"\x00\x00" * gap)
            timeline.append({"text": sent, "start": pos / SR, "end": (pos + n) / SR})
            section_durs[si] += (n + gap) / SR
            pos += n + gap
    return narration, timeline, section_durs
