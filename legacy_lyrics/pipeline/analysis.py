"""Find the "hook": the most-repeated, high-energy 25-30 s stretch of the song.

There is no public per-section play data, so this is a proxy: sections that repeat most
(typically the chorus/mukhda) and are loudest score highest. Start/end snap to beats.
"""
import subprocess
from pathlib import Path

import numpy as np


def to_wav(src, dst: Path, sr=22050):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1",
                    "-ar", str(sr), str(dst)], check=True)


def _norm_cols(x):
    x = x - x.mean(axis=1, keepdims=True)
    return x / (np.linalg.norm(x, axis=0, keepdims=True) + 1e-9)


def find_hook(wav: Path, cfg):
    import librosa
    from scipy.ndimage import uniform_filter1d

    c, a = cfg["clip"], cfg["analysis"]
    y, sr = librosa.load(str(wav), sr=22050, mono=True)
    dur = len(y) / sr
    if dur <= c["max_seconds"]:
        return 0.0, dur, {"note": "track shorter than max clip; using the whole track", "duration": dur}

    hop = 2048
    fps = sr / hop
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=13)[1:]
    feat = np.vstack([_norm_cols(chroma), 0.5 * _norm_cols(mfcc)]) / np.sqrt(1.25)
    feat = _norm_cols(feat)
    n = feat.shape[1]
    sim = feat.T @ feat

    # repetition score: best sustained similarity with any frame at least `gap` seconds away
    gap = int(a["min_repeat_gap_seconds"] * fps)
    k = max(3, int(a["smooth_seconds"] * fps))
    rep = np.zeros(n)
    for lag in range(gap, n - k):
        d = uniform_filter1d(np.diagonal(sim, lag), k, mode="nearest")
        rep[: n - lag] = np.maximum(rep[: n - lag], d)
        rep[lag:] = np.maximum(rep[lag:], d)

    rms = librosa.feature.rms(y=y, hop_length=hop)[0][:n]
    rms = uniform_filter1d(rms, k, mode="nearest")
    rms = np.clip(rms / (np.percentile(rms, 95) + 1e-9), 0, 1)
    score = rep + a["energy_weight"] * rms

    w = int(c["target_seconds"] * fps)
    lo = int(a["intro_skip_seconds"] * fps)
    hi = n - w - int(a["outro_skip_seconds"] * fps)
    if hi <= lo:
        lo, hi = 0, max(0, n - w)
    csum = np.concatenate([[0], np.cumsum(score)])
    wins = (csum[w:] - csum[:-w])[lo: hi + 1] / w
    start_f = lo + int(np.argmax(wins))
    start, end = start_f / fps, start_f / fps + c["target_seconds"]

    # snap to beats
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop, units="time")
    beats = np.asarray(beats)
    if len(beats) > 8:
        start = float(beats[np.argmin(np.abs(beats - start))])
        cand = beats[(beats >= start + c["min_seconds"]) & (beats <= start + c["max_seconds"])]
        end = float(cand[np.argmin(np.abs(cand - (start + c["target_seconds"])))]) if len(cand) \
            else start + c["target_seconds"]
    end = min(end, dur)
    info = {"duration": round(dur, 1), "tempo": round(float(np.atleast_1d(tempo)[0]), 1),
            "repetition": round(float(rep[start_f: start_f + w].mean()), 3),
            "window_score": round(float(wins.max()), 3), "beats_found": int(len(beats))}
    return float(start), float(end), info
