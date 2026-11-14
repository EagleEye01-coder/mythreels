"""Stage 4: Ken Burns scenes + narration + burned-in captions -> mp4 (ffmpeg)."""
import random
import subprocess
from pathlib import Path

PAD = 0.6  # seconds of breathing room after each narration


def _run(cmd):
    subprocess.run(cmd, check=True, stderr=subprocess.PIPE)


def _ass_time(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _write_ass(script, lang, durs, cfg, path: Path):
    w, h = cfg["video"]["width"], cfg["video"]["height"]
    font = cfg["languages"][lang]["font"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{font},44,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,3,1,2,60,60,40,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    t, lines = 0.0, []
    for i, scene in enumerate(script["scenes"]):
        d = durs[i] + PAD
        text = scene["narration"][lang].replace("\n", " ")
        lines.append(f"Dialogue: 0,{_ass_time(t)},{_ass_time(t + d)},Default,,0,0,0,,{text}")
        t += d
    path.write_text(head + "\n".join(lines), encoding="utf-8")


def _scene_clip(img: Path, audio: Path, dur: float, idx: int, cfg, out: Path):
    w, h, fps = cfg["video"]["width"], cfg["video"]["height"], cfg["video"]["fps"]
    frames = int(dur * fps)
    fade = cfg["video"]["fade"]
    rnd = random.Random(idx)
    zoom_in = idx % 2 == 0
    # slow zoom in/out with a gentle pan; image is pre-rendered 1.25x so no pixelation
    z = (f"min(zoom+0.0008,1.2)" if zoom_in else f"if(eq(on,0),1.2,max(zoom-0.0008,1.0))")
    x = f"(iw-iw/zoom)*{rnd.choice([0.2, 0.5, 0.8])}"
    y = f"(ih-ih/zoom)*{rnd.choice([0.3, 0.5, 0.7])}"
    vf = (f"scale={w * 2}:-1,zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},"
          f"fade=t=in:st=0:d={fade},fade=t=out:st={dur - fade}:d={fade},format=yuv420p")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(img), "-i", str(audio),
          "-vf", vf, "-af", f"apad=pad_dur={PAD}", "-t", f"{dur}",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
          "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", str(out)])


def render(script, lang, images, audios, durs, cfg, workdir: Path, music: Path | None, out: Path):
    workdir.mkdir(parents=True, exist_ok=True)
    clips = []
    for i, (img, aud, d) in enumerate(zip(images, audios, durs)):
        clip = workdir / f"{lang}_clip_{i:02d}.mp4"
        _scene_clip(img, aud, d + PAD, i, cfg, clip)
        clips.append(clip)
    lst = workdir / f"{lang}_list.txt"
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    joined = workdir / f"{lang}_joined.mp4"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
          "-c", "copy", str(joined)])

    ass = workdir / f"{lang}.ass"
    _write_ass(script, lang, durs, cfg, ass)
    vf = f"ass={ass}"
    if music and music.exists():
        _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-stream_loop", "-1",
              "-i", str(music), "-filter_complex",
              "[1:a]volume=0.08[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
              "-map", "0:v", "-map", "[a]", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
              "-crf", "23", "-c:a", "aac", "-shortest", str(out)])
    else:
        _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-vf", vf,
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "copy", str(out)])
    return out
