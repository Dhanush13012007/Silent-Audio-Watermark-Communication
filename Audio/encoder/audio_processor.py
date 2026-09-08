"""
audio_processor.py
-------------------
Shared audio I/O helpers used by both the encoder and decoder.

Design notes
~~~~~~~~~~~~
The watermark lives in a near-ultrasonic band (default 17.5 kHz - 19.8 kHz),
so we standardise every file to a 44.1 kHz mono float32 signal before doing
any DSP - that gives us a Nyquist frequency of 22.05 kHz, comfortably above
the watermark band with headroom for the FFT bins either side of it.

Any input format ffmpeg understands (wav, mp3, m4a, flac, ogg ...) is
accepted; we shell out to the system ffmpeg binary to normalise everything
to a temp WAV first, which keeps this module free of extra Python deps.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import uuid

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

try:
    from imageio_ffmpeg import get_ffmpeg_exe
except ImportError:
    get_ffmpeg_exe = None

TARGET_SR = 44100


class AudioLoadError(RuntimeError):
    """Raised when an uploaded file can't be decoded as audio."""


def load_audio(path: str, target_sr: int = TARGET_SR) -> tuple[np.ndarray, int]:
    """Load *any* audio file into a mono float32 numpy array in [-1, 1].

    Returns (samples, sample_rate).
    """
    tmp_wav = os.path.join(tempfile.gettempdir(), f"saw_{uuid.uuid4().hex}.wav")
    try:
        try:
            ffmpeg = get_ffmpeg_exe() if get_ffmpeg_exe else "ffmpeg"
            result = subprocess.run(
                [
                    ffmpeg, "-y", "-v", "error",
                    "-i", path,
                    "-ac", "1",                 # mono
                    "-ar", str(target_sr),      # resample
                    "-acodec", "pcm_s16le",
                    tmp_wav,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (FileNotFoundError, RuntimeError):
            if not path.lower().endswith(".wav"):
                raise AudioLoadError(
                    "No audio converter is available. Install the project "
                    "requirements and restart the app to use MP3, M4A, FLAC, "
                    "or OGG files."
                )
            return _load_wav_without_ffmpeg(path, target_sr)

        if result.returncode != 0 or not os.path.exists(tmp_wav):
            raise AudioLoadError(
                f"Could not decode audio file ({result.stderr.strip()[:200]})"
            )

        sr, data = wavfile.read(tmp_wav)
        samples = data.astype(np.float32) / 32768.0
        return samples, sr
    finally:
        if os.path.exists(tmp_wav):
            os.remove(tmp_wav)


def _load_wav_without_ffmpeg(path: str, target_sr: int) -> tuple[np.ndarray, int]:
    """Load common PCM WAV files when the optional ffmpeg binary is absent."""
    try:
        sr, data = wavfile.read(path)
    except (OSError, ValueError) as exc:
        raise AudioLoadError(f"Could not decode WAV file: {exc}") from exc

    if data.ndim == 2:
        data = data.mean(axis=1)
    if np.issubdtype(data.dtype, np.integer):
        info = np.iinfo(data.dtype)
        scale = max(abs(info.min), info.max)
        samples = data.astype(np.float32) / scale
    else:
        samples = data.astype(np.float32)

    if sr != target_sr:
        samples = resample_poly(samples, target_sr, sr).astype(np.float32)
        sr = target_sr
    return np.clip(samples, -1.0, 1.0), sr


def save_audio(path: str, samples: np.ndarray, sr: int = TARGET_SR) -> None:
    """Write a float32 [-1, 1] mono/stereo array out as 16-bit PCM WAV."""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    wavfile.write(path, sr, pcm)


def waveform_preview(samples: np.ndarray, buckets: int = 400) -> list[float]:
    """Downsample a signal to `buckets` peak values for a lightweight
    waveform visualization on the frontend (min/max per bucket, folded
    into a single amplitude so the client can draw a symmetric shape)."""
    if len(samples) == 0:
        return [0.0] * buckets
    chunk = max(1, len(samples) // buckets)
    peaks = []
    for i in range(buckets):
        start = i * chunk
        end = min(start + chunk, len(samples))
        seg = samples[start:end]
        if len(seg) == 0:
            peaks.append(0.0)
        else:
            peaks.append(float(np.max(np.abs(seg))))
    return peaks


def spectrum_snapshot(samples: np.ndarray, sr: int, n_fft: int = 4096) -> dict:
    """Return a magnitude spectrum (dB) for the top portion of the band,
    used to draw the 'signal is silent up here' proof visualization."""
    if len(samples) < n_fft:
        samples = np.pad(samples, (0, n_fft - len(samples)))
    window = np.hanning(n_fft)
    spec = np.fft.rfft(samples[:n_fft] * window)
    mag = np.abs(spec) + 1e-9
    db = 20 * np.log10(mag / np.max(mag))
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    return {"freqs": freqs.tolist(), "db": db.tolist()}


def duration_seconds(samples: np.ndarray, sr: int) -> float:
    return len(samples) / float(sr)
