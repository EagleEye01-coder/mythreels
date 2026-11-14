"""Stage 4: Ken Burns clips per section + synthesized ambient drone + captions -> mp4 (ffmpeg)."""
import subprocess
from pathlib import Path


def _run(cmd):
    subprocess.run(cmd, check=True, stderr=subprocess.PIPE)


def _ass_time(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _write_ass(timeline, cfg, path: Path):
    w, h = cfg["video"]["width"], cfg["video"]["height"]
    font = cfg["language"]["font"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{font},40,&H00E8E8E8,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3,1,2,90,90,45,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = [f"Dialogue: 0,{_ass_time(c['start'])},{_ass_time(c['end'] + 0.15)},Default,,0,0,0,,{c['text']}"
             for c in timeline]
    path.write_text(head + "\n".join(lines), encoding="utf-8")


def _section_clip(img: Path, dur: float, idx: int, cfg, out: Path):
    w, h, fps = cfg["video"]["width"], cfg["video"]["height"], cfg["video"]["fps"]
    frames = max(2, int(dur * fps))
    fade, zoom = cfg["video"]["fade"], cfg["video"]["zoom"]
    if idx % 2 == 0:
        z = f"1+{zoom}*on/{frames}"
    else:
        z = f"1+{zoom}-{zoom}*on/{frames}"
    px = f"{0.25 + 0.5 * (idx % 3) / 2:.2f}+0.2*on/{frames}"
    x = f"(iw-iw/zoom)*({px})"
    y = "(ih-ih/zoom)*0.5"
    vf = (f"scale={w * 2}:-1,zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},"
          f"noise=alls=6:allf=t,eq=brightness=-0.03:saturation=0.85,"
          f"fade=t=in:st=0:d={fade},fade=t=out:st={max(0, dur - fade):.2f}:d={fade},format=yuv420p")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(img), "-vf", vf, "-an",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", str(out)])


def _ambient(total: float, out: Path):
    t = f"{total:.2f}"
    _run(["ffmpeg", "-y", "-loglevel", "error",
          "-f", "lavfi", "-i", f"anoisesrc=d={t}:c=brown:a=0.5:r=24000",
          "-f", "lavfi", "-i", f"sine=f=55:d={t}:r=24000",
          "-filter_complex",
          f"[0:a]lowpass=f=250[n];[1:a]volume=0.5,tremolo=f=0.2:d=0.7[s];"
          f"[n][s]amix=inputs=2:duration=first,afade=t=in:d=4,afade=t=out:st={max(0, total - 4):.2f}:d=4[a]",
          "-map", "[a]", "-ac", "1", str(out)])


def render(script, images, narration: Path, timeline, section_durs, cfg, workdir: Path, out: Path):
    workdir.mkdir(parents=True, exist_ok=True)
    total = sum(section_durs)

    clips = []
    for i, (img, d) in enumerate(zip(images, section_durs)):
        clip = workdir / f"clip_{i:02d}.mp4"
        _section_clip(img, d, i, cfg, clip)
        clips.append(clip)
    lst = workdir / "list.txt"
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    joined = workdir / "joined.mp4"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
          "-c", "copy", str(joined)])

    amb = workdir / "ambient.wav"
    _ambient(total, amb)
    mix = workdir / "mix.wav"  # narration + ambient, loudness-normalised (reused for the podcast MP3)
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(narration), "-i", str(amb),
          "-filter_complex",
          "[0:a]volume=1.0[n];[1:a]volume=0.22[b];"
          "[n][b]amix=inputs=2:duration=first:dropout_transition=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]",
          "-map", "[a]", "-ar", "44100", "-ac", "1", str(mix)])

    ass = workdir / "captions.ass"
    _write_ass(timeline, cfg, ass)
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-i", str(mix),
          "-filter_complex", f"[0:v]ass={ass}[v]", "-map", "[v]", "-map", "1:a",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
          "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)])
    return out, mix
