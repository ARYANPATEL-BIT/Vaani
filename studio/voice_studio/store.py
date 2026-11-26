"""Where a user's voice lives on disk, and the provenance log.

Layout, under [data_dir] (backend/data/studio, gitignored):

    <user id>/reference.wav    the enrolled sample, 24 kHz mono (Chatterbox's rate)
    <user id>/embedding.npy    its speaker embedding (ETH-3: stored with consent)
    <user id>/consent.json     the consent text, word for word, and when
    <user id>/generated/*.wav  every file generated in this voice
    provenance.jsonl           one line per generation, for every user (ETH-5)

The user id is the first 16 hex characters of sha256(email). A hash, not the
email, so no email address ends up in a folder name, and every character is
safe in a path whatever the address contains.

Deleting a voice (ETH-4) removes the whole <user id> folder: sample,
embedding, consent and generated audio, in one call. provenance.jsonl is
kept: it holds no audio and no text, only a user id, a time, a hash of the
script and a duration, and it is what the daily cap is counted from. A user
who deletes and re-enrols must not get a fresh quota.

Enrolment writes consent.json LAST. A voice counts as enrolled only when it
exists, so a crash halfway through an enrolment leaves a voice that is not
enrolled, never an enrolled voice without its consent record.
"""

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

CONSENT = "consent.json"
REFERENCE = "reference.wav"
EMBEDDING = "embedding.npy"
GENERATED = "generated"
PROVENANCE = "provenance.jsonl"


def user_id(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()[:16]


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def folder(self, uid: str) -> Path:
        return self.root / uid

    def reference_path(self, uid: str) -> Path:
        return self.folder(uid) / REFERENCE

    def consent(self, uid: str) -> dict | None:
        """The consent record, or None if this user has no enrolled voice."""
        path = self.folder(uid) / CONSENT
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save_enrolment(
        self,
        uid: str,
        samples: np.ndarray,
        rate: int,
        embedding: np.ndarray,
        consent: dict,
    ) -> None:
        folder = self.folder(uid)
        folder.mkdir(parents=True, exist_ok=True)
        sf.write(folder / REFERENCE, samples, rate, subtype="PCM_16")
        np.save(folder / EMBEDDING, embedding)
        # Last, so "enrolled" can never be true without the rest (docstring).
        (folder / CONSENT).write_text(
            json.dumps(consent, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )

    def save_generation(
        self, uid: str, generation_id: str, samples: np.ndarray, rate: int, note: str
    ) -> Path:
        """Write one generated file, with `note` in its WAV comment (ETH-5)."""
        folder = self.folder(uid) / GENERATED
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{generation_id}.wav"
        # WAV files can carry text tags (a LIST/INFO chunk). soundfile writes
        # them only if they are set before the first sample is written.
        with sf.SoundFile(path, "w", rate, 1, subtype="PCM_16", format="WAV") as f:
            f.software = "Vaani voice studio"
            f.comment = note
            f.write(samples)
        return path

    def delete(self, uid: str) -> bool:
        """Remove everything stored for this voice. True if there was any."""
        folder = self.folder(uid)
        if not folder.exists():
            return False
        shutil.rmtree(folder)
        return True

    def log_generation(self, record: dict) -> None:
        # newline="\n": LF on every OS (Windows would otherwise write CRLF).
        with (self.root / PROVENANCE).open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record) + "\n")

    def generations_since(self, uid: str, since: float) -> int:
        """How many generations this user made after `since` (unix time)."""
        path = self.root / PROVENANCE
        if not path.exists():
            return 0
        count = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            count += record["user"] == uid and record["time"] >= since
        return count
