"""
アーティファクト向けチェックサム計算。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO


class ChecksumCalculator:
    """
    SHA256 チェックサムを計算するユーティリティ。
    """

    def __init__(self, chunk_size: int = 1024 * 1024) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size は正の値である必要があります。")
        self._chunk_size = chunk_size

    def from_path(self, path: Path) -> str:
        with path.open("rb") as fh:
            return self.from_stream(fh)

    def from_stream(self, stream: BinaryIO) -> str:
        digest = hashlib.sha256()
        while True:
            chunk = stream.read(self._chunk_size)
            if not chunk:
                break
            digest.update(chunk)
        return digest.hexdigest()

