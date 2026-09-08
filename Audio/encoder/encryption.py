"""Sender-side hybrid encryption for watermark payloads."""

from __future__ import annotations

import os
import struct

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import load_pem_public_key

MAGIC = b"SAW1"
RSA_KEY_BYTES = 256


def encrypt(data: bytes, public_key_pem: str) -> bytes:
    """Encrypt data for the receiver identified by a PEM public key."""
    if not public_key_pem.strip():
        raise ValueError("A receiver RSA public key is required.")
    try:
        public_key = load_pem_public_key(public_key_pem.encode("utf-8"))
        aes_key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        ciphertext = AESGCM(aes_key).encrypt(nonce, data, MAGIC)
        wrapped_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("The receiver public key is not a valid PEM key.") from exc
    if len(wrapped_key) != RSA_KEY_BYTES:
        raise ValueError("Use a 2048-bit RSA receiver public key.")
    return MAGIC + struct.pack(">H", len(wrapped_key)) + wrapped_key + nonce + ciphertext
