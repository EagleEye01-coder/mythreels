"""Stage 3: narration per scene via edge-tts (free). Returns audio paths + durations."""
import asyncio
import subprocess
from pathlib import Path


def duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)], text=True)
    return float(out.strip())


async def _synth(text, voice, path):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate="-8%").save(str(path))  # slightly slow for kids


def generate(script, lang, cfg, outdir: Path, dry=False):
    outdir.mkdir(parents=True, exist_ok=True)
    voice = cfg["languages"][lang]["voice"]
    paths = []
    for i, scene in enumerate(script["scenes"]):
        text = scene["narration"][lang]
        p = outdir / f"{lang}_{i:02d}.mp3"
        paths.append(p)
        if p.exists() and p.stat().st_size > 1000:
            continue
        if dry:  # silent clip, length ~ text length
            secs = max(3, len(text) / 14)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            "anullsrc=r=24000:cl=mono", "-t", str(secs), "-q:a", "9", str(p)],
                           check=True)
        else:
            for attempt in range(3):
                try:
                    asyncio.run(_synth(text, voice, p))
                    break
                except Exception:
                    if attempt == 2:
                        raise
    return paths, [duration(p) for p in paths]
