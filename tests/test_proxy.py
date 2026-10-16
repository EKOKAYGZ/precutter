"""Preview proxies: generation, atomicity, range serving, single-flight."""
import os
import shutil
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from precutter import app as app_module
from precutter import config
from precutter import proxy as proxy_mod

client = TestClient(app_module.app)


def _ffmpeg():
    return (os.environ.get("PRECUTTER_TEST_FFMPEG")
            or shutil.which("ffmpeg"))


needs_ffmpeg = pytest.mark.skipif(
    not _ffmpeg(), reason="ffmpeg not available")


@pytest.fixture()
def two_track(monkeypatch, tmp_path):
    ff = _ffmpeg()
    if not ff:
        pytest.skip("ffmpeg not available")
    monkeypatch.setattr(app_module.config, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(app_module.config, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(config, "FFMPEG_BIN", ff)
    src = tmp_path / "two.mp4"
    r = subprocess.run(
        [ff, "-hide_banner", "-y",
         "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10:duration=6",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
         "-f", "lavfi", "-i", "sine=frequency=880:duration=6",
         "-map", "0:v", "-map", "1:a", "-map", "2:a",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-shortest", str(src)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    return src


@needs_ffmpeg
def test_build_track_audio_atomic(two_track):
    outdir = proxy_mod.proxy_dir("two")
    name = proxy_mod.build_track_audio(two_track, 1, outdir)
    assert name in ("track1.ogg", "track1.m4a")
    final = outdir / name
    assert final.stat().st_size > 1024
    assert not list(outdir.glob("*.part"))
    # Second call reuses cache (no rebuild).
    assert proxy_mod.build_track_audio(two_track, 1, outdir) == name


@needs_ffmpeg
def test_proxy_job_lifecycle_and_range(two_track):
    # Bu test video proxy yolunu da kapsıyor: isteği açık tut.
    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_module.config, "PREVIEW_VIDEO_PROXY", True)
    try:
        resp = client.post("/proxy", json={"filename": "two.mp4"})
        assert resp.status_code == 200, resp.text
        job_id = resp.json()["job_id"]
        deadline = time.time() + 180
        while time.time() < deadline:
            job = client.get(f"/jobs/{job_id}").json()
            if job["status"] in ("done", "error"):
                break
            time.sleep(0.5)
        assert job["status"] == "done", job
        assert job["result"]["ready"] is True
        assert set(job["result"]["audio"]) >= {"0", "1"}
        assert job["result"]["video"] == "proxy.mp4"

        st = client.get("/proxy/two.mp4").json()
        assert st["ready"] is True

        full = client.get("/proxy-audio/two.mp4", params={"track": 0})
        assert full.status_code == 200
        assert len(full.content) > 1024
        part = client.get("/proxy-audio/two.mp4", params={"track": 0},
                          headers={"Range": "bytes=0-1023"})
        assert part.status_code == 206, part.status_code
        assert part.headers.get("content-range", "").startswith("bytes 0-1023/")
        assert len(part.content) == 1024

        vid = client.get("/proxy-video/two.mp4")
        assert vid.status_code == 200
        assert len(vid.content) > 1024
        vid_part = client.get("/proxy-video/two.mp4",
                              headers={"Range": "bytes=0-1023"})
        assert vid_part.status_code == 206

        assert client.get("/proxy-audio/two.mp4",
                          params={"track": 9}).status_code == 404
    finally:
        monkey.undo()


@needs_ffmpeg
def test_proxy_job_skips_video_when_disabled(two_track):
    """preview_video kapalıyken iş sadece sesi yapar (analizi bekleterek
    720p yeniden kodlamaz) ve video endpoint'i 404 döner."""
    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_module.config, "PREVIEW_VIDEO_PROXY", False)
    try:
        resp = client.post("/proxy", json={"filename": "two.mp4"})
        assert resp.status_code == 200, resp.text
        job_id = resp.json()["job_id"]
        deadline = time.time() + 180
        while time.time() < deadline:
            job = client.get(f"/jobs/{job_id}").json()
            if job["status"] in ("done", "error"):
                break
            time.sleep(0.5)
        assert job["status"] == "done", job
        assert set(job["result"]["audio"]) >= {"0", "1"}
        assert job["result"]["video"] is None
        assert client.get("/proxy-video/two.mp4").status_code == 404
    finally:
        monkey.undo()


@needs_ffmpeg
def test_proxy_single_flight(monkeypatch, two_track):
    import time as _t

    orig = proxy_mod.build_track_audio

    def slow(*a, **k):
        _t.sleep(3)
        return orig(*a, **k)

    monkeypatch.setattr(proxy_mod, "build_track_audio", slow)
    first = client.post("/proxy", json={"filename": "two.mp4"}).json()
    second = client.post("/proxy", json={"filename": "two.mp4"}).json()
    assert second["job_id"] == first["job_id"]
    assert second.get("deduped") is True


@needs_ffmpeg
def test_video_proxy_reports_progress(two_track):
    from precutter import proxy as proxy_mod

    outdir = proxy_mod.proxy_dir("two_prog")
    seen = []
    name = proxy_mod.build_video_proxy(
        two_track, outdir, duration=6.0, progress=seen.append)
    assert name == "proxy.mp4"
    assert seen and seen[-1] == 1.0
    assert all(0.0 <= v <= 1.0 for v in seen)
