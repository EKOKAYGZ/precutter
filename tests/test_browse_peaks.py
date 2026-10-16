"""Server file browser."""
from fastapi.testclient import TestClient

from precutter import app as app_module

client = TestClient(app_module.app)


def test_browse_roots_shape():
    resp = client.get("/browse")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data) >= {"cwd", "parent", "roots", "dirs", "files"}


def test_browse_lists_videos_only(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.mp4").write_bytes(b"0" * 16)
    (tmp_path / "b.mkv").write_bytes(b"0" * 16)
    (tmp_path / "note.txt").write_bytes(b"x")
    resp = client.get("/browse", params={"path": str(tmp_path)})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["cwd"] == str(tmp_path)
    assert [d["name"] for d in data["dirs"]] == ["sub"]
    assert sorted(f["name"] for f in data["files"]) == ["a.mp4", "b.mkv"]
    assert data["files"][0]["size_bytes"] == 16


def test_browse_rejects_missing():
    assert client.get("/browse", params={"path": "Z:\\nope\\no"}).status_code == 400


def test_proxy_status_reads_existing_files(monkeypatch, tmp_path):
    """Üretilmiş proxy dosyaları durumdan okunur (üretim yok)."""
    from precutter import app as app_module

    monkeypatch.setattr(app_module.config, "WORKSPACE_DIR", tmp_path)
    d = tmp_path / "previews" / "abc123"
    d.mkdir(parents=True)
    (d / "track0.ogg").write_bytes(b"0" * 2048)
    (d / "track1.m4a").write_bytes(b"0" * 2048)
    from precutter import proxy as proxy_mod

    st = proxy_mod.status("abc123", [0, 1])
    assert st["ready"] is True
    assert st["audio"] == {0: "track0.ogg", 1: "track1.m4a"}
    assert st["video"] is None
    st2 = proxy_mod.status("abc123", [0, 1, 2])
    assert st2["ready"] is False
