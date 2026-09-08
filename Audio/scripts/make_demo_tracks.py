"""
Generates a couple of short, pleasant ambient host tracks so judges can try
the demo instantly without hunting for an audio file. Run once:

    python3 scripts/make_demo_tracks.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from encoder.audio_processor import save_audio

SR = 44100
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "audio")
os.makedirs(OUT_DIR, exist_ok=True)


def envelope(n, attack=0.05, release=0.3):
    env = np.ones(n)
    a = int(n * attack)
    r = int(n * release)
    if a > 0:
        env[:a] *= np.linspace(0, 1, a)
    if r > 0:
        env[-r:] *= np.linspace(1, 0, r)
    return env


def ambient_pad(duration, chord, sr=SR, seed=0):
    rng = np.random.default_rng(seed)
    n = int(duration * sr)
    t = np.arange(n) / sr
    signal = np.zeros(n)
    for freq in chord:
        detune = 1 + rng.normal(0, 0.0015)
        signal += np.sin(2 * np.pi * freq * detune * t)
        signal += 0.3 * np.sin(2 * np.pi * freq * 2 * detune * t)
    signal /= len(chord)
    signal *= envelope(n)
    noise = rng.normal(0, 0.01, n)
    signal = signal * 0.5 + noise
    return (signal / (np.max(np.abs(signal)) + 1e-9) * 0.6).astype(np.float32)


def piano_riff(duration, notes, sr=SR, seed=1):
    n_total = int(duration * sr)
    signal = np.zeros(n_total)
    note_len = duration / len(notes)
    for i, freq in enumerate(notes):
        n = int(note_len * sr)
        t = np.arange(n) / sr
        tone = np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * freq * 2 * t)
        tone *= np.exp(-t * 3.2)
        start = int(i * note_len * sr)
        signal[start : start + n] += tone[: len(signal[start : start + n])]
    return (signal / (np.max(np.abs(signal)) + 1e-9) * 0.7).astype(np.float32)


if __name__ == "__main__":
    pad = ambient_pad(20, chord=[220.0, 277.18, 329.63])  # A minor-ish pad
    save_audio(os.path.join(OUT_DIR, "ambient_pad.wav"), pad, SR)

    notes = [261.63, 293.66, 329.63, 392.00, 329.63, 293.66, 261.63, 220.0] * 2
    riff = piano_riff(20, notes)
    save_audio(os.path.join(OUT_DIR, "piano_riff.wav"), riff, SR)

    print("Wrote demo tracks to", OUT_DIR)
