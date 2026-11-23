"""Lyrics for the chosen window: Whisper transcription with word timestamps (free, CPU).

Old recordings are noisy, so output is imperfect. The transcript is saved next to the video and
low-confidence results are flagged for your approval check.
"""
import re

DEV = re.compile(r"[ऀ-ॿ]")


def transcribe(clip_wav, cfg, dry=False, duration=28.0):
    """-> (lines, meta). line = {start, end, text, words:[{w,start,end}]} (times relative to clip)."""
    if dry:
        n = 6
        step = (duration - 3) / n
        lines = [{"start": 1.0 + i * step, "end": 1.0 + (i + 1) * step - 0.3,
                  "text": f"lyric line {i + 1} stub text", "words": []} for i in range(n)]
        return lines, {"confidence": "dry-run", "needs_review": False}

    from faster_whisper import WhisperModel
    model = WhisperModel(cfg["whisper"]["model"], device="cpu", compute_type="int8")
    segs, info = model.transcribe(str(clip_wav), language=cfg["whisper"]["language"],
                                  word_timestamps=True, beam_size=5,
                                  condition_on_previous_text=False)
    segs = list(segs)
    lines, logprobs, nwords = [], [], 0
    for s in segs:
        words = [{"w": w.word.strip(), "start": float(w.start), "end": float(w.end)}
                 for w in (s.words or []) if w.word.strip()]
        if not words:
            continue
        logprobs.append(s.avg_logprob)
        nwords += len(words)
        for i in range(0, len(words), 7):           # at most ~7 words per on-screen line
            chunk = words[i:i + 7]
            lines.append({"start": chunk[0]["start"], "end": chunk[-1]["end"],
                          "text": " ".join(w["w"] for w in chunk), "words": chunk})
    avg = sum(logprobs) / len(logprobs) if logprobs else -9.0
    text = " ".join(l["text"] for l in lines)
    dev = len(DEV.findall(text))
    needs_review = avg < -0.9 or nwords < 8 or dev < 0.5 * max(1, len(re.findall(r"\w", text)))
    return lines, {"confidence": round(avg, 2), "words": nwords, "needs_review": needs_review}
