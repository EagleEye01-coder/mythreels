"""Old-song lyric reel generator. Usage:
    python main.py --dry              # offline: synthetic song, stub lyrics
    python main.py                    # first todo song in songs.yaml
    python main.py --song my-song-1   # a specific song
"""
import argparse
import datetime
import json
from pathlib import Path

import yaml

from pipeline import analysis, lyrics, render, rights

ROOT = Path(__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--song")
    a = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    work = ROOT / "work"
    work.mkdir(exist_ok=True)

    if a.dry:
        from pipeline import dryrun
        audio, meta = dryrun.make_song(work / "dry_song.mp3")
        song = {"id": "dry-test", "title": "Dry Test Song", "film": "Test Film", "audio": str(audio),
                "recording_year": 1930, "lyricist": {"name": "Test Lyricist", "death_year": 1940},
                "composers": [{"name": "Test Composer", "death_year": 1945}]}
        print(f"Synthetic chorus starts at {meta['chorus_starts']} s, length {meta['chorus_len']} s")
    else:
        songs = (yaml.safe_load((ROOT / "songs.yaml").read_text(encoding="utf-8")) or {}).get("songs") or []
        todo = [s for s in songs if (s["id"] == a.song if a.song else s.get("status", "todo") == "todo")]
        if not todo:
            print("No songs to process. Add an entry to songs.yaml (see the template in that file).")
            return
        song = todo[0]

    out = ROOT / "output" / song["id"]
    out.mkdir(parents=True, exist_ok=True)
    print(f"Song: {song['title']} ({song['film']}, {song['recording_year']})")

    ok, evidence = rights.check(song)
    for line in evidence:
        print("  rights:", line)
    if not ok:
        print("::error::Rights gate failed. Add a licence_note only if you hold written permission.")
        (out / "result.json").write_text(json.dumps({"song": song["id"], "blocked": True,
                                                      "rights": evidence}, indent=2, ensure_ascii=False))
        raise SystemExit(2)

    audio = Path(song["audio"])
    if not audio.is_absolute():
        audio = ROOT / audio
    if not audio.exists():
        raise SystemExit(f"::error::Audio file not found: {song['audio']}")

    wav = work / f"{song['id']}.wav"
    analysis.to_wav(audio, wav)
    start, end, info = analysis.find_hook(wav, cfg)
    dur = end - start
    print(f"Hook window: {start:.1f}s - {end:.1f}s ({dur:.1f}s) {info}")

    clip = work / f"{song['id']}_clip.wav"
    render.cut_audio(audio, start, dur, clip)
    lines, lmeta = lyrics.transcribe(clip, cfg, dry=a.dry, duration=dur)
    print(f"Lyrics: {len(lines)} lines, {lmeta}")
    if lmeta.get("needs_review"):
        print("::warning::Low-confidence lyrics. Check the transcript before posting.")
    (out / "transcript.txt").write_text("\n".join(l["text"] for l in lines), encoding="utf-8")

    mp4 = out / f"{song['id']}.mp4"
    render.render(clip, lines, song, dur, cfg, work / "tmp", mp4)
    (out / "result.json").write_text(json.dumps({
        "song": song["id"], "window": [round(start, 2), round(end, 2)], "analysis": info,
        "lyrics": lmeta, "rights": evidence, "rendered": str(mp4.name),
        "generated": datetime.datetime.now().isoformat(timespec="seconds")},
        indent=2, ensure_ascii=False))
    print(f"Rendered {mp4}")


if __name__ == "__main__":
    main()
