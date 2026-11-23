"""Render a 9:16 lyric video: dark vintage background, karaoke-style highlighted lines, credits."""
import subprocess
from pathlib import Path


def _run(cmd):
    subprocess.run(cmd, check=True, stderr=subprocess.PIPE)


def _t(t):
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _background(path: Path, w, h):
    from PIL import Image, ImageDraw, ImageFilter
    img = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(img)
    for y in range(h):  # warm dark gradient
        k = y / h
        px.line([(0, y), (w, y)], fill=(int(38 - 22 * k), int(18 - 10 * k), int(14 - 7 * k)))
    vig = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vig).ellipse([-w * 0.25, -h * 0.05, w * 1.25, h * 1.05], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(160))
    img = Image.composite(img, Image.new("RGB", (w, h), (4, 2, 2)), vig)
    img.save(path, quality=92)


def _karaoke(line, event_start):
    """ASS text with \\kf sweep per word; falls back to even spread when no word times."""
    words = line["words"]
    if not words:
        toks = line["text"].split()
        span = max(0.4, line["end"] - event_start)
        per = span / max(1, len(toks))
        words = [{"w": t, "start": event_start + i * per, "end": event_start + (i + 1) * per}
                 for i, t in enumerate(toks)]
    cursor, out = event_start, []
    for i, wd in enumerate(words):
        end = words[i + 1]["start"] if i + 1 < len(words) else wd["end"]
        out.append(f"{{\\kf{max(1, round((end - cursor) * 100))}}}{wd['w']} ")
        cursor = max(cursor, end)
    return "".join(out).strip()


def _ass(lines, credit, dur, cfg, path: Path):
    v, s = cfg["video"], cfg["style"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {v['width']}
PlayResY: {v['height']}
WrapStyle: 0

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Lyric,{s['font']},{s['font_size']},{s['highlight']},{s['base']},&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,4,2,5,110,110,0,1
Style: Credit,{s['font']},{s['credit_size']},&H00B8B8B8,&H00B8B8B8,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,2,1,2,80,80,330,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    ev = [f"Dialogue: 0,{_t(0)},{_t(dur)},Credit,,0,0,0,,{{\\fad(600,600)}}{credit}"]
    for i, ln in enumerate(lines):
        start = max(0.0, ln["start"] - 0.2)
        end = ln["end"] + 0.5
        if i + 1 < len(lines):
            end = min(end, lines[i + 1]["start"] - 0.2 + 0.1)
        end = max(end, start + 0.6)
        ev.append(f"Dialogue: 1,{_t(start)},{_t(end)},Lyric,,0,0,0,,{{\\fad(200,250)}}{_karaoke(ln, start)}")
    path.write_text(head + "\n".join(ev), encoding="utf-8")


def cut_audio(src, start, dur, out: Path):
    fade_out = max(0.0, dur - 1.2)
    _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
          "-af", f"afade=t=in:d=0.4,afade=t=out:st={fade_out:.2f}:d=1.2,loudnorm=I=-14:TP=-1.5:LRA=11",
          "-ar", "44100", "-ac", "2", str(out)])


def render(clip_wav: Path, lines, song, dur, cfg, workdir: Path, out: Path):
    workdir.mkdir(parents=True, exist_ok=True)
    v = cfg["video"]
    bg = workdir / "bg.jpg"
    _background(bg, v["width"], v["height"])
    lyr = song["lyricist"]["name"]
    mus = ", ".join(c["name"] for c in song["composers"])
    credit = f"{song['title']} ({song['film']}, {song['recording_year']})\\NLyrics: {lyr}  |  Music: {mus}"
    ass = workdir / "lyrics.ass"
    _ass(lines, credit, dur, cfg, ass)
    frames = int(dur * v["fps"])
    vf = (f"scale={v['width'] * 2}:-1,zoompan=z='1+0.05*on/{frames}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2'"
          f":d={frames}:s={v['width']}x{v['height']}:fps={v['fps']},"
          f"noise=alls=4:allf=t,eq=saturation=0.85,format=yuv420p,ass={ass}")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(bg), "-i", str(clip_wav), "-vf", vf,
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-maxrate", "6M", "-bufsize", "12M",
          "-c:a", "aac", "-b:a", "160k",
          "-movflags", "+faststart", "-shortest", str(out)])
    return out
