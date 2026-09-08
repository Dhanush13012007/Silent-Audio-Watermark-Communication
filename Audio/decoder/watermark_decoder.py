"""
watermark_decoder.py
----------------------
Turns a candidate sync position into an actual recovered message.

For each bit slot after the sync tone, we measure signal energy at the two
FSK tones (BIT0_FREQ / BIT1_FREQ) using a single-bin DFT (the Goertzel
algorithm's closed form) evaluated only at those two frequencies - much
cheaper than a full FFT since we only care about two exact bins. Whichever
frequency has more energy in that window is the bit.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

from decoder.decryption import decrypt
from decoder.watermark_detector import find_sync_candidates, overall_confidence
from encoder.watermark_encoder import (
    BIT0_FREQ,
    BIT1_FREQ,
    BIT_DURATION,
    SYNC_DURATION,
)

HEADER_BITS = 16
CRC_BITS = 32


@dataclass
class DecodeResult:
    success: bool
    message: str = ""
    reason: str = ""
    confidence: float = 0.0
    candidates_tried: int = 0
    matched_offset_seconds: float = 0.0
    payload_bytes: int = 0
    bit_error_hint: bool = False
    snr_db: float = field(default=0.0)


@lru_cache(maxsize=8)
def _basis(n: int, sr: int, freq: float) -> tuple[np.ndarray, np.ndarray]:
    idx = np.arange(n)
    return np.cos(2 * np.pi * freq * idx / sr), np.sin(2 * np.pi * freq * idx / sr)


def _bin_energy(samples: np.ndarray, sr: int, freq: float) -> float:
    n = len(samples)
    cos_c, sin_c = _basis(n, sr, freq)
    real = float(np.dot(samples, cos_c))
    imag = float(np.dot(samples, sin_c))
    return real * real + imag * imag


def _read_bits(audio: np.ndarray, sr: int, start: int, n_bits: int) -> tuple[list[int], float]:
    bit_len = int(round(BIT_DURATION * sr))
    bits = []
    margins = []
    for i in range(n_bits):
        s = start + i * bit_len
        e = s + bit_len
        if e > len(audio):
            raise IndexError("Ran out of samples while reading bits.")
        window = audio[s:e]
        e0 = _bin_energy(window, sr, BIT0_FREQ)
        e1 = _bin_energy(window, sr, BIT1_FREQ)
        bits.append(1 if e1 > e0 else 0)
        total = e0 + e1 + 1e-12
        margins.append(abs(e1 - e0) / total)
    avg_margin = float(np.mean(margins)) if margins else 0.0
    return bits, avg_margin


def _bits_to_bytes(bits: list[int]) -> bytes:
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for b in bits[i : i + 8]:
            byte = (byte << 1) | b
        out.append(byte)
    return bytes(out)


def decode_message(audio: np.ndarray, sr: int, password: str = "") -> DecodeResult:
    candidates = find_sync_candidates(audio, sr)
    if not candidates:
        return DecodeResult(
            success=False,
            reason="No ultrasonic sync beacon detected - this track doesn't appear to carry a watermark.",
            confidence=0.0,
        )

    confidence = overall_confidence(candidates)
    bit_len = int(round(BIT_DURATION * sr))
    sync_len = int(round(SYNC_DURATION * sr))
    # Higher number = more diagnostically useful reason to surface if every
    # candidate ultimately fails.
    best_reason = ""
    best_reason_rank = -1
    saw_bit_errors = False

    for candidate in candidates:
        bit_start = candidate.start_sample + sync_len
        try:
            header_bits, _ = _read_bits(audio, sr, bit_start, HEADER_BITS)
            payload_len = struct.unpack(">H", _bits_to_bytes(header_bits))[0]

            if payload_len == 0 or payload_len > 4096:
                if best_reason_rank < 1:
                    best_reason = (
                        "A sync-like tone was detected, but no valid watermark frame "
                        "was found. Upload the watermarked output file and use the "
                        "same passphrase used during encoding."
                    )
                    best_reason_rank = 1
                continue

            payload_bit_start = bit_start + HEADER_BITS * bit_len
            payload_bits, avg_margin = _read_bits(
                audio, sr, payload_bit_start, payload_len * 8
            )
            payload_bytes = _bits_to_bytes(payload_bits)

            crc_bit_start = payload_bit_start + payload_len * 8 * bit_len
            crc_bits, _ = _read_bits(audio, sr, crc_bit_start, CRC_BITS)
            crc_read = struct.unpack(">I", _bits_to_bytes(crc_bits))[0]

            plaintext = decrypt(payload_bytes, password)
            crc_calc = zlib.crc32(plaintext) & 0xFFFFFFFF

            if crc_calc == crc_read:
                message = plaintext.decode("utf-8", errors="replace")
                snr_db = 10 * np.log10(max(candidate.score, 1e-6))
                return DecodeResult(
                    success=True,
                    message=message,
                    confidence=max(confidence, 60.0),
                    candidates_tried=candidates.index(candidate) + 1,
                    matched_offset_seconds=candidate.start_sample / sr,
                    payload_bytes=payload_len,
                    snr_db=float(snr_db),
                )
            else:
                if best_reason_rank < 2:
                    saw_bit_errors = avg_margin < 0.3
                    best_reason = (
                        "A watermark-like signal was detected, but the message could "
                        "not be verified. Check that you uploaded the watermarked "
                        "file and entered the same passphrase."
                    )
                    best_reason_rank = 2
        except (IndexError, struct.error):
            if best_reason_rank < 0:
                best_reason = "Sync found near the end of the track - not enough samples left to read a full frame."
                best_reason_rank = 0
            continue

    reason = best_reason or "Watermark energy detected but no valid frame could be decoded."
    if saw_bit_errors:
        reason += " This usually means the wrong password was used, or the audio was heavily compressed/edited after watermarking."
    return DecodeResult(
        success=False,
        reason=reason,
        confidence=confidence,
        candidates_tried=len(candidates),
        bit_error_hint=saw_bit_errors,
    )
