"""Synthetic stand-in song for offline tests: verse A, louder repeating chorus B, no real music."""
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 22050


def _phrase(notes, beat, amp):
    out = []
    for f in notes:
        t = np.arange(int(SR * beat)) / SR
        env = np.minimum(1, t * 30) * np.exp(-t * 2.5)
        out.append(amp * env * (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * 2 * f * t)))
    return np.concatenate(out)


def make_song(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1)
    verse_notes = [rng.choice([220, 247, 262, 294, 330]) for _ in range(32)]
    chorus_notes = [392, 440, 494, 440, 392, 330, 392, 440] * 4
    beat = 0.5
    parts = [_phrase(verse_notes, beat, 0.25), _phrase(chorus_notes, beat, 0.6),
             _phrase([rng.choice([220, 262, 330]) for _ in range(32)], beat, 0.25),
             _phrase(chorus_notes, beat, 0.6), _phrase(chorus_notes, beat, 0.6)]
    sig = np.concatenate(parts)
    wav = path.with_suffix(".wav")
    sf.write(wav, sig, SR)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), str(path)], check=True)
    return path, {"chorus_starts": [16.0, 48.0, 64.0], "chorus_len": 16.0, "total": len(sig) / SR}
