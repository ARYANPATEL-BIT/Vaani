"""Download the Piper voices named in config.toml and verify their sha256.

The voices (.onnx, about 63 MB each) are too large to commit, so every
machine that synthesises speech - a laptop, Samyak's, CI - fetches them with
this script. Everything comes from [tts.piper]: the repository URL (pinned to
one revision), the folder to save in, and per persona the voice name and the
sha256 it must have. A voice two personas share is fetched once.

Name persona keys to fetch only their voices. CI fetches only "default": the
one voice its tests load (the other voices' tests read only the committed
.onnx.json files), so a cold CI run downloads 63 MB, not every voice.

Fails loud: a wrong hash exits with status 1 and deletes the download, so a
corrupted or swapped file never sits where the server will load it. A file
already in place with the right hash is left alone (nothing is downloaded).

    uv run python scripts/fetch_models.py            # every persona's voice
    uv run python scripts/fetch_models.py default    # CI
"""

import argparse
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


def voice_url(base: str, voice: str) -> str:
    """Where piper-voices keeps a voice, built from its name the way piper's
    own downloader does: hi_IN-priyamvada-medium ->
    hi/hi_IN/priyamvada/medium/hi_IN-priyamvada-medium.onnx"""
    locale, speaker, quality = voice.split("-", 2)
    family = locale.split("_")[0]
    return f"{base}/{family}/{locale}/{speaker}/{quality}/{voice}.onnx"


def fetch(url: str, target: Path, sha256: str) -> bool:
    """True if `target` ends up in place with the right hash."""
    if target.exists() and sha256_of(target) == sha256:
        print(f"ok: {target.name} already present, sha256 matches")
        return True

    # Download beside the target, then rename: an interrupted download never
    # leaves a half-written file under the real name.
    part = target.with_name(target.name + ".part")
    digest = hashlib.sha256()
    print(f"downloading {url}")
    # follow_redirects: Hugging Face answers /resolve/ with a redirect to its
    # file storage. The timeout is per network step, not for the whole file.
    with httpx.stream("GET", url, follow_redirects=True, timeout=30) as r:
        r.raise_for_status()
        with part.open("wb") as f:
            for block in r.iter_bytes(BLOCK):
                digest.update(block)
                f.write(block)

    actual = digest.hexdigest()
    if actual != sha256:
        part.unlink()
        print(
            f"FAILED: {target.name} has sha256 {actual}, "
            f"config.toml expects {sha256}. Download deleted.",
            file=sys.stderr,
        )
        return False
    part.replace(target)
    print(f"ok: saved {target} ({target.stat().st_size:,} bytes), sha256 matches")
    return True


def main(personas: list[str]) -> int:
    cfg = get_settings().tts.piper
    unknown = set(personas) - cfg.voices.keys()
    if unknown:
        print(f"FAILED: no voice for persona(s) {sorted(unknown)}", file=sys.stderr)
        return 1
    # (voice, sha256) pairs, each once, in config order.
    wanted = dict.fromkeys(
        (v.voice, v.sha256)
        for persona, v in cfg.voices.items()
        if not personas or persona in personas
    )
    models_dir = BACKEND_ROOT / cfg.models_dir
    ok = True
    for voice, sha256 in wanted:
        url = voice_url(cfg.voices_url, voice)
        ok = fetch(url, models_dir / f"{voice}.onnx", sha256) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("personas", nargs="*", help="persona keys (default: all)")
    sys.exit(main(parser.parse_args().personas))
