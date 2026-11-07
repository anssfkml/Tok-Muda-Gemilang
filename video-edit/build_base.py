"""Cut, retime, reframe and grade the raw clips into one 1080x1920 base video.

Each segment is rendered on its own (low memory), then the parts are concatenated.

usage: python3 build_base.py <drone> <facade> <hometour> <workdir> <out.mp4>
"""
import os
import subprocess
import sys

from timeline import SEGMENTS, W, H, FPS

drone, facade, hometour, work, out = sys.argv[1:6]
srcs = {"drone": drone, "facade": facade, "hometour": hometour}
os.makedirs(work, exist_ok=True)

GRADE = ("eq=contrast=1.05:saturation=1.15:brightness=0.01,"
         "colorbalance=rm=0.03:gm=0.0:bm=-0.03:rh=0.02:bh=-0.02")

parts = []
for n, (sid, src, a, b, sp) in enumerate(SEGMENTS):
    nframes = round((b - a) / sp * FPS)
    sharpen = ",unsharp=5:5:0.6" if src == "drone" else ""  # drone is 720p, upscaled
    vf = (f"setpts=PTS/{sp},fps={FPS},"
          f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},"
          f"setsar=1{sharpen},{GRADE},format=yuv420p")
    p = os.path.join(work, f"seg{n:02d}_{sid}.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-t", str(b - a + 0.5),
                    "-i", srcs[src], "-an", "-vf", vf, "-frames:v", str(nframes),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "14", "-r", str(FPS), p],
                   check=True)
    parts.append(p)

lst = os.path.join(work, "concat.txt")
with open(lst, "w") as f:
    f.writelines(f"file '{p}'\n" for p in parts)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                "-c", "copy", out], check=True)
