"""
decryption.py
--------------
Mirrors encoder/encryption.py. The cipher is a symmetric XOR keystream, so
decrypt() and encrypt() are the same operation - this module exists as its
own file so the decode pipeline doesn't need to reach into the encoder
package to reverse the payload, keeping the two pipelines independent.
"""

from __future__ import annotations

import hashlib


def _keystream(key: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(key + counter.to_bytes(4, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _derive_key(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).digest()


def decrypt(data: bytes, password: str) -> bytes:
    if not password:
        return data
    key = _derive_key(password)
    stream = _keystream(key, len(data))
    return bytes(a ^ b for a, b in zip(data, stream))
