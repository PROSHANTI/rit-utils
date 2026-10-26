import hashlib
import json
import sqlite3

import pytest

from deploy.pi.inventory_backup import BackupError, InventoryBackup, NextcloudPublisher, NoRedirect
from src.utils.inventory.models import InventoryItem
from src.utils.inventory.repository import InventoryRepository


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "source.sqlite3"
    store = InventoryRepository(path)
    store.add(InventoryItem(article="1", name="Backup test", quantity=4))
    store.create_snapshot()
    return path


def properties(size):
    return (
        f'<d:multistatus xmlns:d="DAV:"><d:response><d:propstat><d:prop>'
        f"<d:getcontentlength>{size}</d:getcontentlength></d:prop><d:status>HTTP/1.1 200 OK</d:status>"
        f"</d:propstat></d:response></d:multistatus>"
    ).encode()


def test_online_snapshot_reads_wal_and_preserves_source(database, tmp_path, monkeypatch):
    with sqlite3.connect(database) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("UPDATE inventory_products SET quantity=9")
        writer.commit()
        before = hashlib.sha256(database.read_bytes()).hexdigest()
        monkeypatch.setattr(NextcloudPublisher, "__init__", lambda self: None)
        monkeypatch.setattr(NextcloudPublisher, "publish", lambda self, path: {"ok": True, "sha256Verified": True})
        backup = InventoryBackup(database, tmp_path / "backups")
        report = backup.run()
        assert report["ok"] and report["sourceReadOnly"] and report["integrity"] == "ok"
        assert hashlib.sha256(database.read_bytes()).hexdigest() == before
        with sqlite3.connect(tmp_path / "backups/inventory.sqlite3") as restored:
            assert restored.execute("SELECT quantity FROM inventory_products").fetchone()[0] == 9
            assert restored.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            assert restored.execute("SELECT COUNT(*) FROM inventory_history").fetchone()[0] == 1
        assert json.loads((tmp_path / "backups/status.json").read_text())["ok"]


def test_cloud_failure_preserves_local_copy_and_marks_status_failed(database, tmp_path, monkeypatch):
    monkeypatch.setattr(NextcloudPublisher, "__init__", lambda self: None)

    def fail(self, path):
        raise BackupError("webdav_get_http_403")

    monkeypatch.setattr(NextcloudPublisher, "publish", fail)
    backup = InventoryBackup(database, tmp_path / "backups")
    with pytest.raises(BackupError):
        backup.run()
    assert (tmp_path / "backups/inventory.sqlite3").is_file()
    report = json.loads((tmp_path / "backups/status.json").read_text())
    assert report["ok"] is False and report["errorCode"] == "webdav_get_http_403"


def test_missing_source_is_not_created_and_failure_is_recorded(tmp_path):
    backup = InventoryBackup(tmp_path / "missing.sqlite3", tmp_path / "backups")
    with pytest.raises(BackupError, match="source_missing"):
        backup.run()
    assert not backup.source.exists()
    assert json.loads((backup.destination / "status.json").read_text())["ok"] is False


@pytest.fixture
def publisher(monkeypatch):
    monkeypatch.setenv("NEXTCLOUD_WEBDAV_USERNAME", "test-user")
    monkeypatch.setenv("NEXTCLOUD_WEBDAV_PASSWORD", "test-password")
    return NextcloudPublisher()


def test_webdav_upload_is_downloaded_and_index_verified(database, publisher, monkeypatch):
    payload = database.read_bytes()
    replies = iter([(404, b""), (405, b""), (201, b""), (200, payload), (207, properties(len(payload)))])
    calls = []

    def request(method, **kwargs):
        calls.append((method, kwargs))
        return next(replies)

    monkeypatch.setattr(publisher, "request", request)
    report = publisher.publish(database)
    assert [method for method, _ in calls] == ["GET", "MKCOL", "PUT", "GET", "PROPFIND"]
    assert report["sha256Verified"] and report["indexVerified"] and not report["unchangedUploadSkipped"]
    assert calls[2][1]["data"] == payload


def test_unchanged_cloud_copy_is_not_uploaded_again(database, publisher, monkeypatch):
    payload = database.read_bytes()
    replies = iter([(200, payload), (207, properties(len(payload)))])
    calls = []

    def request(method, **kwargs):
        calls.append(method)
        return next(replies)

    monkeypatch.setattr(publisher, "request", request)
    assert publisher.publish(database)["unchangedUploadSkipped"]
    assert calls == ["GET", "PROPFIND"]


@pytest.mark.parametrize("failure", ["hash", "index"])
def test_webdav_verification_rejects_corrupt_download_or_wrong_index(database, publisher, monkeypatch, failure):
    payload = database.read_bytes()
    replies = (
        iter([(200, b"corrupt"), (201, b""), (200, b"wrong")])
        if failure == "hash"
        else iter([(200, payload), (207, properties(1))])
    )
    monkeypatch.setattr(publisher, "request", lambda *args, **kwargs: next(replies))
    with pytest.raises(BackupError, match="verification_failed|size_mismatch"):
        publisher.publish(database)


def test_credentials_missing_and_redirects_are_rejected(monkeypatch):
    monkeypatch.delenv("NEXTCLOUD_WEBDAV_USERNAME", raising=False)
    monkeypatch.delenv("NEXTCLOUD_WEBDAV_PASSWORD", raising=False)
    with pytest.raises(BackupError, match="credentials_missing"):
        NextcloudPublisher()
    with pytest.raises(BackupError, match="redirect_refused"):
        NoRedirect().redirect_request(None, None, 302, "", None, "https://other.example")
