"""Enrolment routes: POST /studio/challenge and POST /studio/enrol.

ETH-1 (own voice only), ETH-2 (live challenge, speaker match) and ETH-3
(consent stored with the embedding) are all enforced here, in one request,
in this order, cheapest check first:

  1. consent: the posted consent text must be exactly the configured text,
     which the page only sends when the box is ticked;
  2. a live challenge phrase exists for this user (issued < ttl ago);
  3. the sample decodes, is 10 to 30 s long and is quiet enough (SNR);
  4. the challenge recording decodes, is short enough and quiet enough;
  5. Whisper hears the challenge phrase in it (WHAT was said);
  6. its speaker embedding matches the sample's (WHO said it).

Only when all six pass is anything written. Any failure is a 4xx with a
message that tells the user what to change, and nothing is stored.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Form, Request, UploadFile

from voice_studio.access import StudioError, Writer, studio_of
from voice_studio.audio_checks import AudioError, decode, duration_s, snr_db, to_pcm16
from voice_studio.verify import cosine, is_live, new_challenge, phrase_match

log = logging.getLogger("voice_studio.enrol")
router = APIRouter(prefix="/studio")

CHECK_RATE = 16_000  # Whisper, the voice encoder and the SNR check all use 16 kHz
STORE_RATE = 24_000  # Chatterbox's own rate, so it never resamples the sample


@router.post("/challenge")
async def challenge(request: Request, user: Writer) -> dict:
    """A fresh random phrase for this user, replacing any earlier one."""
    studio = studio_of(request)
    cfg = studio.cfg
    issued = new_challenge(cfg.challenge_words, cfg.challenge_word_count)
    studio.challenges[user.uid] = issued
    return {"phrase": issued.phrase, "expires_in_s": cfg.challenge_ttl_s}


async def _read(upload: UploadFile, limit: int, what: str) -> bytes:
    # Starlette has already spooled the upload to a temporary file; its size
    # is known before we pull it into memory.
    if upload.size is not None and upload.size > limit:
        mb = limit // 10**6
        raise StudioError(
            413, "STUDIO_FILE_TOO_LARGE", f"The {what} file is over {mb} MB."
        )
    return await upload.read()


def _decode(data: bytes, rate: int, what: str) -> np.ndarray:
    try:
        return decode(data, rate)
    except AudioError as exc:
        raise StudioError(
            422,
            "STUDIO_BAD_AUDIO",
            f"The {what} could not be read ({exc}). Record again, or upload a "
            "WAV, M4A, MP3 or WebM file.",
        ) from exc


def _require_quiet(samples: np.ndarray, min_db: float, what: str) -> float:
    snr = snr_db(samples, CHECK_RATE)
    if snr < min_db:
        raise StudioError(
            422,
            "STUDIO_LOW_SNR",
            f"The {what} is too noisy, or has no clear speech: its signal-to-noise "
            f"ratio is {snr:.0f} dB and it needs {min_db:.0f} dB. Move to a quiet "
            "room, turn off fans and AC, hold the mic a hand-width from your mouth, "
            "and speak at a normal volume.",
        )
    return snr


@router.post("/enrol")
async def enrol(
    request: Request,
    sample: UploadFile,
    challenge: UploadFile,
    user: Writer,
    consent_text: Annotated[str, Form()] = "",
) -> dict:
    studio = studio_of(request)
    cfg = studio.cfg

    # 1. Consent (ETH-3): no consent, no enrolment, and nothing is even read.
    if consent_text != cfg.consent_text:
        raise StudioError(
            422,
            "STUDIO_CONSENT_REQUIRED",
            "Tick the consent box first: a voice is only enrolled with consent.",
        )
    # 2. The challenge must be one we issued to this user, recently.
    pending = studio.challenges.get(user.uid)
    if not is_live(pending, cfg.challenge_ttl_s):
        raise StudioError(
            409,
            "STUDIO_NO_CHALLENGE",
            "Your challenge phrase has expired. Get a new phrase and record it again.",
        )

    # 3. The voice sample.
    sample_bytes = await _read(sample, cfg.max_upload_bytes, "voice sample")
    voice = _decode(sample_bytes, CHECK_RATE, "voice sample")
    seconds = duration_s(voice, CHECK_RATE)
    if not cfg.sample_min_s <= seconds <= cfg.sample_max_s:
        raise StudioError(
            422,
            "STUDIO_BAD_LENGTH",
            f"The voice sample is {seconds:.1f} s long; it must be "
            f"{cfg.sample_min_s:.0f} to {cfg.sample_max_s:.0f} s. Record again.",
        )
    snr = _require_quiet(voice, cfg.min_snr_db, "voice sample")

    # 4. The challenge recording.
    phrase_audio = _decode(
        await _read(challenge, cfg.max_upload_bytes, "challenge"),
        CHECK_RATE,
        "challenge recording",
    )
    if duration_s(phrase_audio, CHECK_RATE) > cfg.challenge_max_s:
        raise StudioError(
            422,
            "STUDIO_BAD_LENGTH",
            f"The challenge recording is over {cfg.challenge_max_s:.0f} s. "
            "Record just the phrase.",
        )
    _require_quiet(phrase_audio, cfg.min_snr_db, "challenge recording")

    # 5. WHAT was said. The cancellation token is the Recognizer contract
    # (vaani/asr/base.py); five words take about a second, so nothing sets it.
    heard = await studio.recognizer.transcribe(to_pcm16(phrase_audio), asyncio.Event())
    heard_text = heard.text if heard else ""
    match = phrase_match(pending.phrase, heard_text)
    if match < cfg.min_challenge_match:
        raise StudioError(
            422,
            "STUDIO_CHALLENGE_MISMATCH",
            f'We heard "{heard_text}", which is not the phrase on screen. Read the '
            "phrase clearly, in one take, then try again.",
        )

    # 6. WHO said it. The encoder is CPU work, so it runs on a worker thread
    # and the event loop keeps serving other requests meanwhile.
    voice_vec = await asyncio.to_thread(studio.encoder.embed, voice)
    phrase_vec = await asyncio.to_thread(studio.encoder.embed, phrase_audio)
    similarity = cosine(voice_vec, phrase_vec)
    if similarity < cfg.min_speaker_similarity:
        raise StudioError(
            422,
            "STUDIO_SPEAKER_MISMATCH",
            "The voice reading the phrase does not match the voice in the sample. "
            "Only your own voice can be enrolled: record both yourself, with the "
            "same microphone if you can.",
        )

    consent = {
        "email": user.email,
        "name": user.name,
        "consent_text": consent_text,
        "consented_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "challenge_phrase": pending.phrase,
        "challenge_heard": heard_text,
        "challenge_match": round(match, 2),
        "speaker_similarity": round(similarity, 3),
        "sample_snr_db": round(snr, 1),
        "sample_seconds": round(seconds, 1),
        "model": f"{cfg.hf_repo}@{cfg.hf_revision} {cfg.t3_model}",
    }
    stored = _decode(sample_bytes, STORE_RATE, "voice sample")
    studio.store.save_enrolment(user.uid, stored, STORE_RATE, voice_vec, consent)
    studio.challenges.pop(user.uid, None)  # one phrase, one enrolment
    # The user id, never the email, in logs.
    log.info(
        "enrolled %s: %.1f s, snr %.1f dB, match %.2f, similarity %.3f",
        user.uid,
        seconds,
        snr,
        match,
        similarity,
    )
    return {
        "enrolled": True,
        "enrolled_at": consent["consented_at"],
        "duration_s": consent["sample_seconds"],
        "snr_db": consent["sample_snr_db"],
        "challenge_match": consent["challenge_match"],
        "speaker_similarity": consent["speaker_similarity"],
    }
