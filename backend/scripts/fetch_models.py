"""Download the Piper voice named in config.toml and verify its sha256.

The voice (.onnx, 63.5 MB) is too large to commit, so every machine that
synthesises speech - a laptop, Samyak's, CI - fetches it with this script.
Everything comes from [tts.piper]: the URL (pinned to one repository
revision), where to save it, and the sha256 it must have.

Fails loud: a wrong hash exits with status 1 and deletes the download, so a
corrupted or swapped file never sits where the server will load it. A file
already in place with the right hash is left alone (nothing is downloaded).

    uv run python scripts/fetch_models.py
"""

import hashlib
import sys
from pathlib import Path

import httpx

from vaani.config import get_settings

BACKEND_ROOT = Path(__file__).resolve().parent.parent
# Read and hash 1 MB at a time, so the whole file is never in memory.
BLOCK = 1 << 20


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(BLOCK):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    cfg = get_settings().tts.piper
    target = BACKEND_ROOT / cfg.model_path
    if target.exists() and sha256_of(target) == cfg.model_sha256:
        print(f"ok: {target.name} already present, sha256 matches")
        return 0

    # Download beside the target, then rename: an interrupted download never
    # leaves a half-written file under the real name.
    part = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    print(f"downloading {cfg.model_url}")
    # follow_redirects: Hugging Face answers /resolve/ with a redirect to its
    # file storage. The timeout is per network step, not for the whole file.
    with httpx.stream("GET", cfg.model_url, follow_redirects=True, timeout=30) as r:
        r.raise_for_status()
        with part.open("wb") as f:
            for block in r.iter_bytes(BLOCK):
                digest.update(block)
                f.write(block)

    actual = digest.hexdigest()
    if actual != cfg.model_sha256:
        part.unlink()
        print(
            f"FAILED: {target.name} has sha256 {actual}, "
            f"config.toml expects {cfg.model_sha256}. Download deleted.",
            file=sys.stderr,
        )
        return 1
    part.replace(target)
    print(f"ok: saved {target} ({target.stat().st_size:,} bytes), sha256 matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
