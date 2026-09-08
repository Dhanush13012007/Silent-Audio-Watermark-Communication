"""
watermark_encoder.py
---------------------
Embeds a text message into a host audio track as a near-ultrasonic,
frequency-shift-keyed (FSK) watermark - inaudible to almost all adult
listeners, invisible in a normal listen-through, but fully recoverable
by `decoder.watermark_decoder` with an FFT sweep of the same band.

Frame layout (all in the ultrasonic sub-band, one tone per slot)
    [ SYNC BEACON ] [ 16-bit LENGTH ] [ payload bits ] [ 32-bit CRC ]

  * SYNC BEACON  - a sustained tone at SYNC_FREQ. The decoder looks for
                    a burst of energy here to find the start of a frame.
  * LENGTH       - number of payload bytes, so the decoder knows exactly
                    how many bits to pull off before the CRC.
  * payload bits - the (optionally encrypted) message, FSK-modulated:
                    BIT0_FREQ for 0, BIT1_FREQ for 1.
  * CRC-32       - lets the decoder confirm the message was recovered
                    correctly (or that the password was right).

The whole frame is generated once, then tiled back-to-back across the
full length of the host track (looping the host if it's shorter than a
single frame). That redundancy means the message survives even if the
final clip is trimmed down, as long as one full frame-length remains.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

import numpy as np

from encoder.encryption import encrypt

# --- Watermark channel parameters -------------------------------------------------
SYNC_FREQ = 19000.0
BIT0_FREQ = 18000.0
BIT1_FREQ = 19600.0
SYNC_DURATION = 0.18          # seconds
BIT_DURATION = 0.04           # seconds per bit (~25 bits/sec)
DEFAULT_AMPLITUDE = 0.06      # fraction of host peak amplitude
FADE_MS = 4                   # raised-cosine edge fade per tone, avoids clicks


@dataclass
class EncodeStats:
    payload_bytes: int
    total_bits: int
    frame_duration: float
    repeats_embedded: int
    output_duration: float
    watermark_band: tuple[float, float]
    bit_rate_bps: float


def _tone(freq: float, duration: float, sr: int, amplitude: float = 1.0) -> np.ndarray:
    n = max(1, int(round(duration * sr)))
    t = np.arange(n) / sr
    wave = np.sin(2 * np.pi * freq * t)
    fade_n = min(n // 2, max(1, int(sr * FADE_MS / 1000)))
    if fade_n > 0:
        window = np.ones(n)
        ramp = 0.5 * (1 - np.cos(np.pi * np.arange(fade_n) / fade_n))
        window[:fade_n] *= ramp
        window[-fade_n:] *= ramp[::-1]
        wave *= window
    return (wave * amplitude).astype(np.float32)


def _bits_from_bytes(data: bytes) -> list[int]:
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def build_frame(message: str, password: str, sr: int) -> tuple[np.ndarray, EncodeStats]:
    """Build one full watermark frame (sync + length + payload + crc) as a
    normalized (peak = 1.0) mono float32 waveform."""
    plaintext = message.encode("utf-8")
    crc = zlib.crc32(plaintext) & 0xFFFFFFFF
    payload = encrypt(plaintext, password) if password else plaintext

    header = struct.pack(">H", len(payload))
    crc_bytes = struct.pack(">I", crc)
    frame_bytes = header + payload + crc_bytes
    bits = _bits_from_bytes(frame_bytes)

    chunks = [_tone(SYNC_FREQ, SYNC_DURATION, sr, 1.0)]
    for bit in bits:
        freq = BIT1_FREQ if bit else BIT0_FREQ
        chunks.append(_tone(freq, BIT_DURATION, sr, 1.0))

    frame = np.concatenate(chunks)
    stats = EncodeStats(
        payload_bytes=len(payload),
        total_bits=len(bits),
        frame_duration=len(frame) / sr,
        repeats_embedded=0,          # filled in by embed_watermark
        output_duration=0.0,
        watermark_band=(BIT0_FREQ - 300, BIT1_FREQ + 300),
        bit_rate_bps=1.0 / BIT_DURATION,
    )
    return frame, stats


def embed_watermark(
    host: np.ndarray,
    sr: int,
    message: str,
    password: str = "",
    amplitude: float = DEFAULT_AMPLITUDE,
) -> tuple[np.ndarray, EncodeStats]:
    """Return (watermarked_audio, stats). `host` must be a mono float32
    array in [-1, 1]."""
    if not message:
        raise ValueError("Message cannot be empty.")

    frame, stats = build_frame(message, password, sr)
    frame_len = len(frame)

    # Extend the host (by looping it) if it's shorter than one full frame,
    # so short demo clips still carry at least one complete message.
    if len(host) < frame_len:
        repeats_needed = int(np.ceil(frame_len / max(1, len(host))))
        host = np.tile(host, repeats_needed)
    host = host[: max(len(host), frame_len)]

    repeats = max(1, len(host) // frame_len)
    tail = len(host) - repeats * frame_len
    watermark_track = np.tile(frame, repeats)
    if tail > 0:
        watermark_track = np.concatenate([watermark_track, frame[:tail]])
    else:
        host = host[: len(watermark_track)]

    host_peak = float(np.max(np.abs(host))) or 1.0
    watermarked = host + watermark_track * (amplitude * host_peak)

    # Guard against clipping from the sum.
    peak = float(np.max(np.abs(watermarked)))
    if peak > 0.99:
        watermarked = watermarked / peak * 0.99

    stats.repeats_embedded = repeats
    stats.output_duration = len(watermarked) / sr
    return watermarked.astype(np.float32), stats
