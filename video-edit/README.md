# Tok Muda Gemilang – TikTok edit

Vertical 1080x1920 / 30fps TikTok edit built from the three raw clips in the shared Drive folder
(Drone, facade, home tour). Raw footage and rendered videos are not committed (too large).

- `timeline.py` – shot list (source, in/out, speed) and TikTok safe zone.
- `build_base.py` – cuts, retimes, reframes and colour-grades the clips into `base.mp4`.
- `music.py` – original synthesised background track (100 BPM, G major), drop synced to the
  school-field reveal and a click sound on the CTA.
- `render.py` – frosted-glass info cards, room labels, centred faded watermark
  (`aniskamalrealty`), contact photo and CTA cursor, then encodes the final video.

```bash
python3 build_base.py drone.mp4 facade.mov hometour.mov work/ base.mp4
python3 music.py music_raw.wav
ffmpeg -i music_raw.wav -af loudnorm=I=-14:TP=-1.5:LRA=11 -ar 44100 music.wav
python3 render.py base.mp4 anis.jpg final.mp4 --audio music.wav
```
