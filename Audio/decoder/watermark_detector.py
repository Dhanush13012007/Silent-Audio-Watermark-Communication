"""
watermark_detector.py
----------------------
Locates candidate watermark frames inside an (unknown-offset) audio track.

The encoder starts every frame with a sustained tone at SYNC_FREQ. To find
it again, we run a matched filter: cross-correlate the incoming audio
against a freshly generated reference tone of the same frequency, sample
rate and duration. Wherever the sync tone actually occurs, the correlation
spikes far above the surrounding noise floor - so the peaks of that
correlation are our candidate frame-start positions, sample-accurate,
regardless of where in the file the frame happens to sit.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import correlate, find_peaks

from encoder.watermark_encoder import SYNC_FREQ, SYNC_DURATION, _tone


@dataclass
class SyncCandidate:
    start_sample: int
    score: float          # correlation peak, relative to the noise floor


def find_sync_candidates(audio: np.ndarray, sr: int, max_candidates: int = 32) -> list[SyncCandidate]:
    ref = _tone(SYNC_FREQ, SYNC_DURATION, sr, amplitude=1.0)
    if len(audio) < len(ref):
        return []

    corr = correlate(audio, ref, mode="valid", method="fft")
    corr_abs = np.abs(corr)

    noise_floor = float(np.median(corr_abs)) + 1e-9
    mad = float(np.median(np.abs(corr_abs - noise_floor))) + 1e-9
    threshold = noise_floor + 6 * mad

    min_distance = max(1, int(sr * SYNC_DURATION * 0.8))
    peaks, props = find_peaks(corr_abs, height=threshold, distance=min_distance)
    if len(peaks) == 0:
        return []

    heights = props["peak_heights"]
    order = np.argsort(-heights)[:max_candidates]

    candidates = [
        SyncCandidate(start_sample=int(peaks[i]), score=float(heights[i] / noise_floor))
        for i in order
    ]
    return candidates


def overall_confidence(candidates: list[SyncCandidate]) -> float:
    """A 0-100 'how confident are we a watermark is present' style score,
    purely for the UI - not used for the actual bit decisions."""
    if not candidates:
        return 0.0
    top = candidates[0].score
    # score is "peak / noise-floor" ratio; squash into a friendly 0-100 range.
    return float(min(100.0, 100.0 * (1 - np.exp(-top / 15.0))))
