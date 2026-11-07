"""Original background track (synthesised, no third-party audio) synced to the edit.

Warm acoustic-pop groove in G major, 100 BPM, I-V-vi-IV. Beat grid is anchored so the
drop lands on the school-field reveal; a mouse-click + ding lands on the CTA click.

usage: python3 music.py <out.wav>
"""
import sys
import wave

import numpy as np

from timeline import TOTAL, seg_times

SR = 44100
BPM = 100
BEAT = 60 / BPM
BAR = 4 * BEAT
T = seg_times()
DROP = T["door"][0] + 1.0              # school field reveal
CLICK = T["cta"][0] + 0.4 + 2.6        # must match render.CTA timing
END = TOTAL
N = int(END * SR) + SR
rng = np.random.default_rng(7)


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def tt(n):
    return np.arange(n) / SR


def env_adsr(n, a=0.005, d=0.1, s=0.7, r=0.1):
    e = np.ones(n) * s
    ai, di, ri = int(a * SR), int(d * SR), int(r * SR)
    ai = max(1, min(ai, n))
    e[:ai] = np.linspace(0, 1, ai)
    dj = min(n, ai + di)
    e[ai:dj] = np.linspace(1, s, dj - ai)
    if ri and n > ri:
        e[-ri:] *= np.linspace(1, 0, ri)
    return e


def fft_filter(x, lo=None, hi=None):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = np.ones_like(f)
    if hi:
        g *= 1 / np.sqrt(1 + (f / hi) ** 4)
    if lo:
        g *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** 4)
    return np.fft.irfft(X * g, len(x))


def add(buf, sig, t0, gain=1.0, pan=0.0):
    i = int(t0 * SR)
    if i >= N:
        return
    sig = sig[: N - i]
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    buf[0, i:i + len(sig)] += sig * gain * l * 1.414
    buf[1, i:i + len(sig)] += sig * gain * r * 1.414


# ------------------------------------------------------------------ instruments
_ks = {}


def pluck(m, dur=1.6, bright=0.5):
    key = (m, dur, bright)
    if key in _ks:
        return _ks[key]
    f = midi(m)
    p = int(SR / f)
    n = int(dur * SR)
    buf = fft_filter(rng.uniform(-1, 1, p * 8), hi=2000 + 6000 * bright)[:p].copy()
    out = np.zeros(n)
    for i in range(n):  # Karplus-Strong
        j = i % p
        v = buf[j]
        out[i] = v
        buf[j] = 0.996 * 0.5 * (v + buf[(j + 1) % p])
    out *= env_adsr(n, 0.002, 0.05, 1.0, 0.08)
    _ks[key] = out / (np.abs(out).max() + 1e-9)
    return _ks[key]


def epiano(m, dur=1.2):
    f = midi(m)
    n = int(dur * SR)
    t = tt(n)
    idx = 1.8 * np.exp(-t / 0.25)
    s = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * t))
    s += 0.25 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.15)
    return s * np.exp(-t / 0.7) * env_adsr(n, 0.004, 0.0, 1.0, 0.12)


def pad_note(m, dur):
    f = midi(m)
    n = int(dur * SR)
    t = tt(n)
    s = np.zeros(n)
    for det in (-0.12, 0.0, 0.11):
        ff = f * 2 ** (det / 12)
        for h in range(1, 9):
            s += np.sin(2 * np.pi * ff * h * t + h) / h
    return s / 8 * env_adsr(n, 0.35, 0.3, 0.8, 0.5)


def bass_note(m, dur):
    f = midi(m)
    n = int(dur * SR)
    t = tt(n)
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) + 0.12 * np.sin(2 * np.pi * 3 * f * t)
    return s * env_adsr(n, 0.006, 0.12, 0.65, 0.06)


def kick():
    n = int(0.4 * SR)
    t = tt(n)
    fr = 45 + 85 * np.exp(-t / 0.03)
    ph = 2 * np.pi * np.cumsum(fr) / SR
    s = np.sin(ph) * np.exp(-t / 0.13)
    s[:200] += rng.uniform(-0.4, 0.4, 200) * np.linspace(1, 0, 200)
    return s


def clap():
    n = int(0.3 * SR)
    t = tt(n)
    nz = fft_filter(rng.uniform(-1, 1, n), lo=900, hi=5000)
    e = np.exp(-t / 0.09)
    for d in (0.0, 0.011, 0.022):
        i = int(d * SR)
        e[i:i + 300] += np.linspace(1, 0, 300)
    return nz * e / 2.2


def hat(open_=False):
    n = int((0.18 if open_ else 0.06) * SR)
    t = tt(n)
    nz = fft_filter(rng.uniform(-1, 1, n), lo=7000)
    return nz * np.exp(-t / (0.06 if open_ else 0.015))


def noise_sweep(dur, rising=True):
    n = int(dur * SR)
    t = tt(n) / dur
    lo = fft_filter(rng.uniform(-1, 1, n), hi=1500)
    hi = fft_filter(rng.uniform(-1, 1, n), lo=3000)
    mix = t if rising else 1 - t
    amp = t ** 2 if rising else np.sin(np.pi * t)
    return (lo * (1 - mix) + hi * mix) * amp


def impact():
    n = int(1.6 * SR)
    t = tt(n)
    fr = 35 + 40 * np.exp(-t / 0.15)
    s = np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-t / 0.5)
    s += fft_filter(rng.uniform(-1, 1, n), lo=2000) * np.exp(-t / 0.35) * 0.35
    return s


def mouse_click():
    n = int(0.06 * SR)
    t = tt(n)
    s = np.sin(2 * np.pi * 2400 * t) * np.exp(-t / 0.004)
    s2 = np.zeros(n)
    k = int(0.035 * SR)
    s2[k:] = np.sin(2 * np.pi * 1800 * t[: n - k]) * np.exp(-t[: n - k] / 0.003) * 0.7
    return s + s2 + fft_filter(rng.uniform(-1, 1, n), lo=3000) * np.exp(-t / 0.003) * 0.6


# ---------------------------------------------------------------------- score
CHORDS = [  # (voicing, bass root)
    ([55, 59, 62, 67], 43),  # G
    ([54, 57, 62, 66], 38),  # D
    ([55, 59, 64, 67], 40),  # Em
    ([55, 60, 64, 67], 36),  # C
]
MELODY = [  # (bar-in-phrase, beat, midi, beats)
    (0, 0, 71, 1), (0, 1, 74, 1), (0, 2, 76, 0.5), (0, 2.5, 74, 0.5), (0, 3, 71, 1),
    (1, 0, 69, 1.5), (1, 1.5, 74, 0.5), (1, 2, 69, 2),
    (2, 0, 67, 1), (2, 1, 71, 1), (2, 2, 76, 1), (2, 3, 74, 1),
    (3, 0, 76, 1.5), (3, 1.5, 74, 0.5), (3, 2, 71, 1), (3, 3, 67, 1),
]
ARP = [0, 1, 2, 3, 2, 1, 2, 3]


def build():
    drums = np.zeros((2, N))
    music = np.zeros((2, N))
    pad = np.zeros((2, N))
    sfx = np.zeros((2, N))
    kenv = np.zeros(N)
    K, C, H, HO = kick(), clap(), hat(), hat(True)

    # intro (before the drop): Cadd9 -> D pad, sparse plucks
    half = DROP / 2
    for notes, t0, d in (([55, 60, 64, 69], 0.0, half + 0.4), ([54, 57, 62, 66], half, DROP - half + 0.6)):
        for m in notes:
            add(pad, pad_note(m, d), t0, 0.05)
    for k, m in enumerate([67, 72, 74, 76, 74, 69]):
        add(music, pluck(m, 1.6, 0.3), k * DROP / 6, 0.22, pan=0.3 * (-1) ** k)
    add(sfx, noise_sweep(1.0, True), DROP - 1.0, 0.18)
    add(sfx, impact(), DROP, 0.55)

    n_bars = int((END - DROP) / BAR)          # full bars after the drop
    last = DROP + n_bars * BAR                 # final chord hit
    for b in range(n_bars):
        t_bar = DROP + b * BAR
        notes, root = CHORDS[b % 4]
        # pad
        for m in notes:
            add(pad, pad_note(m, BAR + 0.3), t_bar, 0.035)
        # bass: 1, (2.5), 3, (4.5)
        for beat, ln, oc in ((0, 1.4, 0), (1.5, 0.45, 12), (2, 1.4, 0), (3.5, 0.45, 7)):
            add(music, bass_note(root + oc, ln * BEAT), t_bar + beat * BEAT, 0.20)
        # pluck arp (8ths), slightly humanised
        for k, ix in enumerate(ARP):
            jitter = rng.uniform(-0.006, 0.006)
            add(music, pluck(notes[ix] + 12, 1.4, 0.55), t_bar + k * BEAT / 2 + jitter,
                0.15 if k % 2 == 0 else 0.11, pan=-0.35 if k % 2 == 0 else 0.35)
        # drums
        for beat in range(4):
            tb = t_bar + beat * BEAT
            if beat in (0, 2):
                add(drums, K, tb, 0.75)
                i = int(tb * SR)
                kenv[i:i + int(0.25 * SR)] = np.maximum(kenv[i:i + int(0.25 * SR)],
                                                         np.linspace(1, 0, len(kenv[i:i + int(0.25 * SR)])))
            if beat in (1, 3):
                add(drums, C, tb, 0.42, pan=0.05)
            add(drums, H, tb, 0.10, pan=0.4)
            add(drums, HO if beat % 2 else H, tb + BEAT / 2, 0.13 if beat % 2 else 0.12, pan=0.4)
        if b % 4 == 3:  # little kick pickup at the end of each phrase
            add(drums, K, t_bar + 3.5 * BEAT, 0.5)
        # melody (e-piano) from bar 4
        if b >= 4:
            for (pb, beat, m, ln) in MELODY:
                if pb == b % 4:
                    add(music, epiano(m, ln * BEAT + 0.8), t_bar + beat * BEAT, 0.13, pan=0.1)

    # ending: G chord hit + ring out
    for m in [55, 59, 62, 67, 71, 74]:
        add(music, pluck(m + 12, 2.5, 0.5), last + rng.uniform(0, 0.03), 0.16, pan=rng.uniform(-0.4, 0.4))
        add(pad, pad_note(m, 2.0), last, 0.03)
    add(music, bass_note(43, 1.5), last, 0.22)
    add(music, epiano(79, 2.0), last, 0.12)
    add(drums, K, last, 0.7)
    add(drums, hat(True), last, 0.2)

    # transitions + CTA click
    for ts in (T["open"][0], T["package"][0], T["cta"][0]):
        add(sfx, noise_sweep(0.5, False), ts - 0.25, 0.10)
    add(sfx, mouse_click(), CLICK, 0.55)
    add(sfx, epiano(91, 0.9), CLICK + 0.06, 0.10)
    add(sfx, epiano(86, 0.9), CLICK + 0.14, 0.08)

    # mix: soft lowpass on pad, sidechain pad+music to kick, reverb send
    pad = np.stack([fft_filter(ch, hi=1800) for ch in pad])
    duck = 1 - 0.35 * kenv
    mix = drums + (music + pad) * duck
    ir_n = int(1.8 * SR)
    ir = rng.uniform(-1, 1, (2, ir_n)) * np.exp(-tt(ir_n) / 0.45)
    ir = np.stack([fft_filter(c, hi=5000) for c in ir])
    send = music + pad * 0.6 + sfx * 0.5
    L = N + ir_n
    rev = np.stack([np.fft.irfft(np.fft.rfft(send[c], L) * np.fft.rfft(ir[c], L), L)[:N] for c in range(2)])
    rev /= np.abs(rev).max() + 1e-9
    mix = mix + sfx + rev * 0.12 * np.abs(mix).max()

    n_end = int(END * SR)
    mix = mix[:, :n_end]
    fade = int(0.9 * SR)
    mix[:, -fade:] *= np.linspace(1, 0, fade) ** 1.5
    mix[:, : int(0.02 * SR)] *= np.linspace(0, 1, int(0.02 * SR))
    mix /= np.abs(mix).max() + 1e-9
    return np.tanh(mix * 1.3) / np.tanh(1.3) * 0.89


def main():
    out = sys.argv[1]
    x = build()
    pcm = (np.clip(x.T, -1, 1) * 32767).astype("<i2")
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    main()
