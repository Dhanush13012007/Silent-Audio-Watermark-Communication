# Silent Channel — Silent Audio Watermark Communication

A hackathon prototype that hides a text message inside an ordinary audio
file. The message rides a band of tones just above human hearing
(18.0–19.6 kHz), mixed in at a whisper. Play the file normally and it
sounds untouched. Run it back through the decoder and the message comes
straight out — checksum-verified, and encrypted for a receiver's public key.

It's a working, self-contained implementation of covert acoustic
communication: real DSP (FSK modulation, matched-filter synchronization,
single-bin DFT demodulation), not a mockup.

## What it actually does

- **Encode**: takes any audio file (or one of two built-in demo tracks),
  turns your message into an ultrasonic tone sequence, and layers it into
  the track at ~5% amplitude. The sender encrypts the payload with the
  receiver's RSA public key before it's ever modulated.
- **Decode**: takes any audio file and the receiver's RSA private key,
  matched-filters it for the sync beacon, demodulates whatever bits are there,
  authenticates and decrypts the payload, and shows you what it found (or a
  specific, honest reason it couldn't).
- **Dashboard**: a running log of every encode/decode run this session,
  with detection confidence and success-rate stats.
- Survives being re-encoded as MP3 at a reasonable bitrate — the
  watermark band is high enough that decent encoders keep it intact.

## Quickstart

```bash
pip install -r requirements.txt
python3 scripts/make_demo_tracks.py   # only needed once, already run — regenerates static/audio/*.wav
python3 app.py
```

Open `http://localhost:5000`. `ffmpeg` must be on your `PATH` (used to
normalize any uploaded format — wav/mp3/m4a/flac/ogg — to 44.1 kHz mono
before processing).

## How the watermark actually works

```
message → AES-GCM encrypt → RSA-OAEP wrap key → frame → FSK modulate → mix into host → output file
```

**Frame layout** (all in the ultrasonic sub-band):

```
[ SYNC BEACON ]  [ 16-bit LENGTH ]  [ payload bits ]  [ 32-bit CRC ]
   19.0 kHz         FSK-coded          FSK-coded         FSK-coded
   180ms tone      18.0/19.6kHz       18.0/19.6kHz      18.0/19.6kHz
```

- Every bit is a 40ms tone: 18.0 kHz for `0`, 19.6 kHz for `1` (~25 bits/sec).
- The whole frame is tiled back-to-back across the entire host track, so
  the message survives even if the file gets trimmed down, as long as one
  full frame-length remains.
- **Encoding a frequency, not a full FFT bin sweep, per bit** keeps
  demodulation cheap: the decoder does a single-bin DFT (a Goertzel-style
  closed form) at exactly the two candidate frequencies for each bit
  window, rather than a full spectrum analysis.
- **Finding the frame** without knowing where it starts is a matched-filter
  problem: the decoder cross-correlates the incoming audio against a
  freshly generated copy of the sync tone. Wherever the real sync tone
  sits, that correlation spikes far above the noise floor — sample-accurate,
  regardless of offset.
- **The encryption** (`encoder/encryption.py` / `decoder/decryption.py`) uses
  AES-GCM for authenticated message encryption and RSA-OAEP to wrap a fresh
  AES key for the receiver. The sender receives only the public key; the
  receiver's private key is required to decrypt and is never embedded in the
  audio.

## Project structure

```
silent-audio-watermark/
├── app.py                        Flask routes + JSON history store
│
├── encoder/
│   ├── watermark_encoder.py      Frame layout, FSK modulation, tiling
│   ├── audio_processor.py        Load/save/resample any format via ffmpeg
│   └── encryption.py             AES-GCM + RSA-OAEP sender encryption
│
├── decoder/
│   ├── watermark_detector.py     Matched-filter sync beacon localization
│   ├── watermark_decoder.py      Bit demodulation, CRC check, full pipeline
│   └── decryption.py             RSA-OAEP + AES-GCM receiver decryption
│
├── static/
│   ├── css/style.css             Design system
│   ├── js/app.js                 All frontend interactivity + canvases
│   └── audio/                    Built-in demo host tracks
│
├── templates/
│   ├── index.html                Landing page + animated spectrogram hero
│   ├── encode.html               Encoder workspace
│   ├── decode.html                Decoder workspace
│   └── dashboard.html             Session telemetry
│
├── scripts/make_demo_tracks.py   Generates the two bundled demo tracks
├── uploads/                       Scratch space for incoming files (not kept)
├── output/                        Generated watermarked files + history.json
├── requirements.txt
└── README.md
```

## Honest limitations (good talking points for judges)

- Sample-rate ceiling: anything transcoded to a sample rate below ~40 kHz
  (e.g. old telephony codecs, some voice-note formats) will low-pass
  filter away the whole watermark band — there's nothing above ~19-20 kHz
  left to find. This is inherent to any near-ultrasonic scheme, not a bug.
- The receiver must generate and protect an RSA private key. Anyone with the
  matching private key can decrypt the embedded message.
- ~25 bits/sec is deliberately conservative for robustness; a
  production system would trade some of that inaudibility margin for
  a denser constellation (more than 2 FSK tones) to raise throughput.
- "Silent" means *very quiet and above most adults' hearing range*, not
  physically inaudible to every listener or microphone — a few younger
  listeners or sensitive equipment may detect a very faint high tone at
  higher amplitude settings.
