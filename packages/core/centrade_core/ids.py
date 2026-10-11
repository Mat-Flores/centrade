"""UUID v7 (RFC 9562, 5.7) : 48 bits de millisecondes Unix puis aléa (absent de la stdlib 3.12)."""

import os
import time
from uuid import UUID


def uuid7() -> UUID:
    n = int.from_bytes(((time.time_ns() // 1_000_000).to_bytes(6, "big")) + os.urandom(10), "big")
    n = (n & ~(0xF << 76)) | (7 << 76)  # version
    n = (n & ~(0x3 << 62)) | (2 << 62)  # variante RFC 4122
    return UUID(int=n)
