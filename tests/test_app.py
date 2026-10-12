"""Test de bout en bout avec une fausse caméra (mire générée par ffmpeg)."""

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from spash import ffmpeg as ff
from spash.app import create_app
from spash.club import Club
from spash.config import Config, Court, LiveConfig


def fake_court(court_id="1"):
    return Court(
        id=court_id,
        name=f"Terrain {court_id}",
        camera_url="testsrc2=size=320x240:rate=25",
        input_args=["-re", "-f", "lavfi"],
        transcode=True,
    )


@pytest.fixture
def cfg(tmp_path):
    cfg = Config(
        club_name="Club test",
        ffmpeg=os.environ.get("SPASH_FFMPEG", ""),
        admin_password="secret",
        data_dir=tmp_path / "data",
        segment_seconds=1,
        highlight_before=2,
        highlight_after=1,
        replay_seconds=2,
        courts=[fake_court()],
        live=LiveConfig(rtmp_url=str(tmp_path / "live.flv"), stream_key="test",
                        width=320, height=240),
    )
    try:
        ff.find_ffmpeg(cfg)
    except RuntimeError:
        pytest.skip("ffmpeg indisponible")
    return cfg


@pytest.fixture
def client(cfg):
    club = Club(cfg)
    with TestClient(create_app(club)) as c:
        c.club = club
        yield c


def wait_for(fn, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.3)
    raise AssertionError("délai dépassé")


def test_court_key_required(client):
    assert client.get("/api/courts/1").status_code == 403
    assert client.get("/api/courts/1?k=faux").status_code == 403
    assert client.get("/api/courts/9?k=x").status_code == 404


def test_admin_requires_password(client):
    assert client.get("/admin").status_code == 401
    assert client.get("/api/admin/overview", auth=("x", "faux")).status_code == 401
    r = client.get("/api/admin/overview", auth=("x", "secret"))
    assert r.status_code == 200
    assert r.json()["courts"][0]["url"].endswith(client.club.court_key("1"))


def test_full_match(client):
    k = client.club.court_key("1")
    base = f"/api/courts/1?k={k}"

    r = client.post(f"/api/courts/1/start?k={k}", json={
        "team_a": "Julie", "team_b": "Marc", "sets_to_win": 1, "games_per_set": 4,
    })
    assert r.status_code == 200, r.text
    token = r.json()["token"]

    # Deuxième démarrage refusé.
    assert client.post(f"/api/courts/1/start?k={k}", json={}).status_code == 409

    for _ in range(3):
        client.post(f"/api/courts/1/point?k={k}", json={"team": 0})
    client.post(f"/api/courts/1/point?k={k}", json={"team": 1})
    r = client.post(f"/api/courts/1/undo?k={k}")
    assert r.json()["score"]["points"] == ["40", "0"]

    time.sleep(3)
    r = client.post(f"/api/courts/1/clip?k={k}", json={"kind": "highlight"})
    assert r.status_code == 200, r.text
    wait_for(lambda: client.get(base).json()["match"]["clips"][0]["status"] == "ready")

    state = client.get(base).json()
    assert state["match"]["team_a"] == "Julie"
    clip_url = state["match"]["clips"][0]["url"]
    clip = client.get(clip_url)
    assert clip.status_code == 200 and len(clip.content) > 1000

    client.post(f"/api/courts/1/point?k={k}", json={"team": 0})  # jeu Julie
    r = client.post(f"/api/courts/1/end?k={k}")
    assert r.status_code == 200
    assert client.get(base).json()["match"] is None

    info = wait_for(lambda: (d := client.get(f"/api/matches/{token}").json())["status"] == "done" and d)
    assert info["duration"] > 2
    assert info["score"]["games"] == [1, 0]
    assert len(info["timeline"]) == 5  # état initial + 4 points
    assert info["timeline"][-1]["t"] > 0

    # Lecture vidéo avec saut dans le temps (requêtes « Range »).
    video = client.get(info["video_url"], headers={"Range": "bytes=0-99"})
    assert video.status_code == 206 and len(video.content) == 100

    folder = client.club.match_dir(1)
    assert (folder / "match.mp4").exists()
    assert not list(folder.glob("seg_*.mkv"))

    assert client.get(f"/m/{token}").status_code == 200
    assert client.get(f"/api/matches/{token}/qr.svg").text.startswith("<svg")
    assert client.get("/api/matches/inconnu").status_code == 404

    # Suppression par le gérant.
    assert client.delete("/api/admin/matches/1", auth=("x", "secret")).status_code == 200
    assert not folder.exists()
    assert client.get(f"/api/matches/{token}").status_code == 404


def test_camera_unreachable(cfg):
    cfg.courts = [Court(id="1", name="T1", camera_url="rtsp://127.0.0.1:9/inexistant")]
    club = Club(cfg)
    with TestClient(create_app(club)) as c:
        k = club.court_key("1")
        r = c.post(f"/api/courts/1/start?k={k}", json={})
        assert r.status_code == 409
        assert "enregistrement" in r.json()["detail"]
        assert c.get(f"/api/courts/1?k={k}").json()["match"] is None


def test_live_stream_with_overlay(client, cfg):
    k = client.club.court_key("1")
    client.post(f"/api/courts/1/start?k={k}", json={"team_a": "A", "team_b": "B"})
    client.post(f"/api/courts/1/point?k={k}", json={"team": 0})
    r = client.post("/api/admin/courts/1/live/start", auth=("x", "secret"))
    assert r.status_code == 200 and r.json()["running"], r.text
    time.sleep(4)
    assert client.club.live_status("1")["running"]
    client.post("/api/admin/courts/1/live/stop", auth=("x", "secret"))
    client.post(f"/api/courts/1/end?k={k}")
    out = Path(cfg.live.rtmp_url)
    assert out.exists() and out.stat().st_size > 10_000


def test_restart_recovers_unfinished_match(cfg):
    club = Club(cfg)
    match = club.start_match("1", "A", "B", {})
    time.sleep(3)
    club.shutdown()  # comme si le PC s'éteignait pendant le match

    club2 = Club(cfg)
    wait_for(lambda: club2.db.get_match(match["id"])["status"] == "done")
    assert club2.match_video(match).exists()
