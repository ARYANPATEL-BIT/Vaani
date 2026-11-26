"""Generation: consent first, caps before the model, provenance after it."""

import io
import json
import time

import soundfile as sf

from tests.conftest import UID
from voice_studio.model_errors import GpuBusy

# "namaste" and a danda, as escapes, so this file and its output stay ASCII.
HINDI = "\u0928\u092e\u0938\u094d\u0924\u0947\u0964"


def provenance(rig) -> list[dict]:
    path = rig.cfg.data_path() / "provenance.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def generate(rig, script="Hello there. How are you?"):
    return rig.client.post("/studio/generate", json={"script": script})


def test_no_enrolment_no_synthesis(rig):
    response = generate(rig)
    assert response.status_code == 403
    assert response.json()["code"] == "STUDIO_NOT_ENROLLED"
    assert rig.cloner.calls == []


def test_generate_returns_a_wav_and_records_provenance(rig):
    rig.enrol()
    response = generate(rig, f"Hello there. {HINDI} Bye!")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "audio/wav"
    # One call, each sentence with its own language (Devanagari -> hi).
    assert rig.cloner.calls == [[("Hello there.", "en"), (HINDI, "hi"), ("Bye!", "en")]]
    with sf.SoundFile(io.BytesIO(response.content)) as wav:
        assert wav.samplerate == 24_000
        # 3 x 0.5 s of sentences + 2 x 0.3 s of gaps.
        assert abs(wav.frames / wav.samplerate - 2.1) < 0.01
        assert wav.comment.startswith("Synthetic speech: Vaani voice studio")
    generated = list((rig.folder / "generated").glob("*.wav"))
    assert len(generated) == 1
    (record,) = provenance(rig)
    assert record["user"] == UID
    assert record["languages"] == ["en", "hi"]
    assert len(record["script_sha256"]) == 64
    assert "Hello" not in json.dumps(record)  # the hash, never the text


def test_script_over_the_cap_is_refused_before_the_model(rig):
    rig.enrol()
    response = generate(rig, "a" * (rig.cfg.max_script_chars + 1))
    assert response.status_code == 422
    assert response.json()["code"] == "STUDIO_SCRIPT_TOO_LONG"
    assert rig.cloner.calls == []


def test_empty_script_is_refused(rig):
    rig.enrol()
    assert generate(rig, "   ").json()["code"] == "STUDIO_SCRIPT_EMPTY"


def test_daily_cap_is_checked_before_the_model(rig):
    rig.enrol()
    for _ in range(rig.cfg.max_generations_per_day):
        rig.studio.store.log_generation({"user": UID, "time": time.time()})
    response = generate(rig)
    assert response.status_code == 429
    assert response.json()["code"] == "STUDIO_CAP_REACHED"
    assert rig.cloner.calls == []


def test_old_generations_do_not_count_toward_the_cap(rig):
    rig.enrol()
    yesterday = time.time() - 25 * 3600
    for _ in range(rig.cfg.max_generations_per_day):
        rig.studio.store.log_generation({"user": UID, "time": yesterday})
    assert generate(rig).status_code == 200


def test_another_users_generations_do_not_count(rig):
    rig.enrol()
    for _ in range(rig.cfg.max_generations_per_day):
        rig.studio.store.log_generation({"user": "someone-else", "time": time.time()})
    assert generate(rig).status_code == 200


def test_one_generation_at_a_time(rig):
    rig.enrol()
    rig.studio.busy = True
    response = generate(rig)
    assert response.status_code == 409
    assert response.json()["code"] == "STUDIO_BUSY"


def test_gpu_out_of_memory_is_a_clear_error_not_a_crash(rig):
    rig.enrol()
    rig.cloner.fail = GpuBusy("out of memory")
    response = generate(rig)
    assert response.status_code == 503
    assert response.json()["code"] == "STUDIO_GPU_BUSY"
    assert rig.studio.busy is False  # the next request can try again
    assert provenance(rig) == []  # a failed generation is not logged
    rig.cloner.fail = None
    assert generate(rig).status_code == 200
