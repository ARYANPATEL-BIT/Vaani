"""ETH-4: one delete removes the sample, the embedding, consent and generated audio."""

from tests.conftest import UID


def test_delete_really_deletes(rig):
    rig.enrol()
    assert (
        rig.client.post("/studio/generate", json={"script": "Hello."}).status_code
        == 200
    )
    assert (rig.folder / "generated").exists()
    rig.challenge()  # a pending phrase too

    response = rig.client.delete("/studio/voice")
    assert response.json() == {"deleted": True}
    assert not rig.folder.exists()  # sample, embedding, consent, generated: all gone
    assert UID not in rig.studio.challenges
    assert rig.client.get("/studio/voice").json()["enrolled"] is False
    # No consent record any more, so no synthesis (ETH-3).
    after = rig.client.post("/studio/generate", json={"script": "Hello."})
    assert after.json()["code"] == "STUDIO_NOT_ENROLLED"


def test_provenance_survives_without_any_voice_data(rig):
    rig.enrol()
    rig.client.post("/studio/generate", json={"script": "Hello."})
    rig.client.delete("/studio/voice")
    log = (rig.cfg.data_path() / "provenance.jsonl").read_text(encoding="utf-8")
    assert UID in log
    assert "Hello" not in log and "me@example.com" not in log


def test_delete_with_nothing_enrolled(rig):
    assert rig.client.delete("/studio/voice").json() == {"deleted": False}


def test_delete_waits_for_a_running_generation(rig):
    rig.enrol()
    rig.studio.busy = True
    response = rig.client.delete("/studio/voice")
    assert response.status_code == 409
    assert (rig.folder / "reference.wav").exists()
