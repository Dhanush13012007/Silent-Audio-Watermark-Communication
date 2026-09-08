"""
app.py
------
Flask entrypoint for the Silent Audio Watermark Communication prototype.

Routes
~~~~~~
  GET  /                 landing page
  GET  /encode            encode UI
  GET  /decode            decode UI
  GET  /dashboard         session stats + history

  POST /api/encode        embed a message into an uploaded audio file
  POST /api/decode        recover a message from an uploaded audio file
  GET  /api/history       JSON history feed for the dashboard
  GET  /api/demo-tracks   list of built-in sample host tracks
  GET  /download/<name>   fetch a generated watermarked file
"""

from __future__ import annotations

import json
import os
import time
import traceback
import uuid
from dataclasses import asdict

from flask import Flask, jsonify, render_template, request, send_from_directory

from encoder.audio_processor import (
    AudioLoadError,
    duration_seconds,
    load_audio,
    save_audio,
    save_audio_mp3,
    spectrum_snapshot,
    waveform_preview,
)
from encoder.watermark_encoder import (
    BIT0_FREQ,
    BIT1_FREQ,
    DEFAULT_AMPLITUDE,
    SYNC_FREQ,
    embed_watermark,
)
from decoder.watermark_decoder import decode_message

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Vercel's deployed project directory is read-only. /tmp is writable for the
# lifetime of a serverless instance and keeps the existing download API intact.
RUNTIME_DIR = os.path.join("/tmp", "silent-audio-watermark") if os.getenv("VERCEL") else BASE_DIR
UPLOAD_DIR = os.path.join(RUNTIME_DIR, "uploads")
OUTPUT_DIR = os.path.join(RUNTIME_DIR, "output")
HISTORY_PATH = os.path.join(OUTPUT_DIR, "history.json")
DEMO_AUDIO_DIR = os.path.join(BASE_DIR, "static", "audio")
MAX_HISTORY = 200
MAX_UPLOAD_MB = 3 if os.getenv("VERCEL") else 60

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # 60 MB uploads


@app.context_processor
def upload_limits() -> dict:
    return {"max_upload_mb": MAX_UPLOAD_MB}


@app.template_filter("fmt_time")
def fmt_time(ts: float) -> str:
    return time.strftime("%b %d, %H:%M:%S", time.localtime(ts))


# ---------------------------------------------------------------- history --
def _load_history() -> list[dict]:
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _append_history(entry: dict) -> None:
    try:
        history = _load_history()
        entry["id"] = uuid.uuid4().hex[:10]
        entry["timestamp"] = time.time()
        history.insert(0, entry)
        history = history[:MAX_HISTORY]
        with open(HISTORY_PATH, "w") as f:
            json.dump(history, f)
    except OSError:
        # Serverless storage is temporary; analytics must not break encoding.
        pass


def _history_summary(history: list[dict]) -> dict:
    encodes = [h for h in history if h["type"] == "encode"]
    decodes = [h for h in history if h["type"] == "decode"]
    successful_decodes = [h for h in decodes if h.get("success")]
    avg_conf = (
        sum(h.get("confidence", 0) for h in decodes) / len(decodes) if decodes else 0.0
    )
    total_chars = sum(h.get("message_length", 0) for h in encodes)
    return {
        "total_operations": len(history),
        "total_encodes": len(encodes),
        "total_decodes": len(decodes),
        "decode_success_rate": (
            round(100 * len(successful_decodes) / len(decodes), 1) if decodes else None
        ),
        "avg_decode_confidence": round(avg_conf, 1),
        "total_characters_hidden": total_chars,
    }


# ------------------------------------------------------------------ pages --
@app.route("/")
def index():
    return render_template("index.html", sync_freq=SYNC_FREQ, bit0=BIT0_FREQ, bit1=BIT1_FREQ)


@app.route("/encode")
def encode_page():
    demo_tracks = _list_demo_tracks()
    return render_template(
        "encode.html",
        demo_tracks=demo_tracks,
        default_amplitude=DEFAULT_AMPLITUDE,
    )


@app.route("/decode")
def decode_page():
    return render_template("decode.html")


@app.route("/dashboard")
def dashboard_page():
    history = _load_history()
    summary = _history_summary(history)
    return render_template("dashboard.html", history=history[:25], summary=summary)


# -------------------------------------------------------------- demo data --
def _list_demo_tracks() -> list[dict]:
    if not os.path.isdir(DEMO_AUDIO_DIR):
        return []
    tracks = []
    for name in sorted(os.listdir(DEMO_AUDIO_DIR)):
        if name.lower().endswith(".wav"):
            label = name.replace(".wav", "").replace("_", " ").title()
            tracks.append({"file": name, "label": label, "url": f"/static/audio/{name}"})
    return tracks


@app.route("/api/demo-tracks")
def api_demo_tracks():
    return jsonify(_list_demo_tracks())


# ------------------------------------------------------------------- APIs --
@app.route("/api/encode", methods=["POST"])
def api_encode():
    started = time.time()
    audio_file = request.files.get("audio")
    demo_track = request.form.get("demo_track", "").strip()
    message = request.form.get("message", "").strip()
    public_key_pem = request.form.get("public_key", "")
    try:
        amplitude = float(request.form.get("amplitude", DEFAULT_AMPLITUDE))
    except ValueError:
        amplitude = DEFAULT_AMPLITUDE
    amplitude = max(0.01, min(amplitude, 0.25))

    if not message:
        return jsonify({"error": "Please enter a message to hide."}), 400
    if len(message.encode("utf-8")) > 800:
        return jsonify({"error": "Message is too long for this demo (max ~800 bytes)."}), 400

    src_path = None
    try:
        if audio_file and audio_file.filename:
            ext = os.path.splitext(audio_file.filename)[1] or ".wav"
            src_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")
            audio_file.save(src_path)
        elif demo_track:
            candidate = os.path.join(DEMO_AUDIO_DIR, demo_track)
            if not os.path.isfile(candidate):
                return jsonify({"error": "Unknown demo track."}), 400
            src_path = candidate
        else:
            return jsonify({"error": "Upload an audio file or pick a demo track."}), 400

        host, sr = load_audio(src_path)
        host_preview = waveform_preview(host)

        # Keep a normalized copy of the original around so the UI can offer
        # a genuine side-by-side A/B listen against the watermarked output.
        original_name = f"original_{uuid.uuid4().hex[:10]}.mp3"
        save_audio_mp3(os.path.join(OUTPUT_DIR, original_name), host, sr)

        watermarked, stats = embed_watermark(
            host, sr, message, public_key_pem=public_key_pem, amplitude=amplitude
        )

        out_name = f"watermarked_{uuid.uuid4().hex[:10]}.mp3"
        out_path = os.path.join(OUTPUT_DIR, out_name)
        save_audio_mp3(out_path, watermarked, sr)

        wm_preview = waveform_preview(watermarked)
        spectrum = spectrum_snapshot(watermarked, sr)

        elapsed = round(time.time() - started, 3)
        _append_history(
            {
                "type": "encode",
                "message_length": len(message),
                "duration_seconds": round(stats.output_duration, 2),
                "repeats_embedded": stats.repeats_embedded,
                "amplitude": amplitude,
                "processing_seconds": elapsed,
                "output_file": out_name,
            }
        )

        return jsonify(
            {
                "success": True,
                "download_url": f"/download/{out_name}",
                "original_url": f"/download/{original_name}",
                "stats": {
                    **asdict(stats),
                    "processing_seconds": elapsed,
                    "sample_rate": sr,
                },
                "waveform_before": host_preview,
                "waveform_after": wm_preview,
                "spectrum": spectrum,
                "watermark_band": [BIT0_FREQ - 300, BIT1_FREQ + 300],
                "sync_freq": SYNC_FREQ,
            }
        )
    except AudioLoadError as e:
        return jsonify({"error": str(e)}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong while embedding the watermark."}), 500
    finally:
        if src_path and audio_file and os.path.exists(src_path):
            try:
                os.remove(src_path)
            except OSError:
                pass


@app.route("/api/decode", methods=["POST"])
def api_decode():
    started = time.time()
    audio_file = request.files.get("audio")
    private_key_pem = request.form.get("private_key", "")

    if not audio_file or not audio_file.filename:
        return jsonify({"error": "Upload an audio file to scan."}), 400

    ext = os.path.splitext(audio_file.filename)[1] or ".wav"
    src_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")
    audio_file.save(src_path)

    try:
        audio, sr = load_audio(src_path)
        result = decode_message(audio, sr, private_key_pem=private_key_pem)
        elapsed = round(time.time() - started, 3)

        _append_history(
            {
                "type": "decode",
                "success": result.success,
                "confidence": round(result.confidence, 1),
                "processing_seconds": elapsed,
                "track_duration": round(duration_seconds(audio, sr), 2),
            }
        )

        payload = asdict(result)
        payload["processing_seconds"] = elapsed
        payload["waveform"] = waveform_preview(audio)
        payload["spectrum"] = spectrum_snapshot(audio, sr)
        payload["watermark_band"] = [BIT0_FREQ - 300, BIT1_FREQ + 300]
        payload["sync_freq"] = SYNC_FREQ
        return jsonify(payload)
    except AudioLoadError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "Something went wrong while scanning the file."}), 500
    finally:
        if os.path.exists(src_path):
            try:
                os.remove(src_path)
            except OSError:
                pass


@app.route("/api/history")
def api_history():
    history = _load_history()
    return jsonify({"summary": _history_summary(history), "recent": history[:25]})


@app.route("/download/<path:filename>")
def download(filename):
    # as_attachment=False so <audio> elements can play these inline; the
    # frontend's download link still forces a save via the HTML `download`
    # attribute on its <a> tag.
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=False)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
