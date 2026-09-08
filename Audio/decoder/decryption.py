"""Receiver-side decryption for the watermark hybrid envelope."""

from __future__ import annotations

import struct

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from encoder.encryption import MAGIC, RSA_KEY_BYTES


def decrypt(data: bytes, private_key_pem: str) -> bytes:
    """Decrypt a sender envelope with the receiver's RSA private key."""
    if not private_key_pem.strip():
        raise ValueError("A receiver RSA private key is required.")
    if len(data) < len(MAGIC) + 2 + RSA_KEY_BYTES + 12 + 16 or data[:4] != MAGIC:
        raise ValueError("This watermark was not encrypted with a receiver key.")
    wrapped_len = struct.unpack(">H", data[4:6])[0]
    if wrapped_len != RSA_KEY_BYTES:
        raise ValueError("The encrypted key envelope is invalid.")
    wrapped_key = data[6 : 6 + wrapped_len]
    nonce = data[6 + wrapped_len : 18 + wrapped_len]
    ciphertext = data[18 + wrapped_len :]
    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"), password=None
        )
        aes_key = private_key.decrypt(
            wrapped_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return AESGCM(aes_key).decrypt(nonce, ciphertext, MAGIC)
    except Exception as exc:
        raise ValueError("The private key is wrong, or the encrypted payload was changed.") from exc
