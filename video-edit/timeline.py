"""Timeline for the Tok Muda Gemilang TikTok edit (1080x1920, 30fps).

Each segment: (source, start_s, end_s, speed). Output duration = (end-start)/speed.
Sources: drone = "Tok Muda Gemilang Drone.MP4", facade = "Tok Muda Gemilang facade",
hometour = "Tok Muda Gemilang home tour" (from the shared Drive folder).
"""

W, H, FPS = 1080, 1920, 30

# TikTok safe zone (UI-free area) for a 1080x1920 frame.
SAFE_L, SAFE_R, SAFE_T, SAFE_B = 60, 940, 210, 1440

SEGMENTS = [
    # id,        src,        start,  end,   speed
    ("hook",     "hometour", 85.5,   88.4,  1.00),  # window view: school field
    ("door",     "hometour", 27.0,   31.0,  1.25),  # back door opens onto school field
    ("open",     "drone",    16.0,   24.0,  2.00),  # drone rises, neighbourhood + school
    ("title",    "facade",    4.0,    8.0,  1.33),  # long row of houses
    ("price",    "drone",     0.0,    6.0,  1.50),  # end-lot exterior
    ("hall",     "hometour",  8.0,   12.0,  1.50),  # ruang tamu
    ("kitchen",  "hometour", 48.0,   51.0,  1.20),  # dapur
    ("bath1",    "hometour", 22.0,   24.0,  1.00),  # bilik air bawah
    ("stairs",   "hometour", 53.5,   56.5,  2.00),  # naik tangga
    ("bed",      "hometour", 66.8,   69.3,  1.00),  # bilik tidur
    ("bath2",    "hometour", 70.0,   72.0,  1.00),  # bilik air atas
    ("package",  "hometour", 12.0,   17.0,  1.25),  # pakej (hall w/ glass door)
    ("amenity",  "drone",    24.0,   31.6,  1.90),  # kemudahan
    ("access",   "facade",    0.0,    4.0,  1.00),  # akses mudah
    ("cta",      "hometour", 86.0,   88.4,  0.40),  # CTA over the window view, slowed
]


def seg_times():
    """Return {id: (t_start, t_end)} on the output timeline."""
    t, out = 0.0, {}
    for sid, _src, a, b, sp in SEGMENTS:
        d = round((b - a) / sp * FPS) / FPS
        out[sid] = (t, t + d)
        t += d
    return out


TOTAL = sum(round((b - a) / sp * FPS) / FPS for _, _, a, b, sp in SEGMENTS)
