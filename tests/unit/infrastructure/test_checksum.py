from io import BytesIO
from pathlib import Path

from infrastructure.storage.checksum import ChecksumCalculator


def test_checksum_from_stream(tmp_path: Path) -> None:
    calculator = ChecksumCalculator(chunk_size=4)
    stream = BytesIO(b"hello world")
    digest = calculator.from_stream(stream)

    assert digest == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    file_path = tmp_path / "data.bin"
    file_path.write_bytes(b"hello world")

    assert calculator.from_path(file_path) == digest

