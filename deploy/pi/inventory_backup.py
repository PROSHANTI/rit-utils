"""Consistent SQLite backup and verified Nextcloud upload. Credentials stay in environment."""

import argparse
import base64
import fcntl
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class BackupError(RuntimeError):
    """A safe diagnostic code without row contents, URLs, credentials or HTTP bodies."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise BackupError("webdav_redirect_refused")


class NextcloudPublisher:
    url = "https://cloud.proshanti.dev/remote.php/dav/files/SHANTI/RIT/Backups/inventory.sqlite3"

    def __init__(self) -> None:
        username = os.environ.get("NEXTCLOUD_WEBDAV_USERNAME", "")
        password = os.environ.get("NEXTCLOUD_WEBDAV_PASSWORD", "")
        if not username or not password:
            raise BackupError("webdav_credentials_missing")
        self.authorization = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(
        self,
        method: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        limit: int = 0,
        folder: bool = False,
    ) -> tuple[int, bytes]:
        target = self.url.rsplit("/", 1)[0] if folder else self.url
        query = urllib.request.Request(
            target,
            data=data,
            method=method,
            headers={
                "Authorization": self.authorization,
                "User-Agent": "RIT Inventory backup",
                **(headers or {}),
            },
        )
        try:
            with self.opener.open(query, timeout=60) as response:
                return response.status, response.read(limit) if limit else b""
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
            if (method == "GET" and status == 404) or (method == "MKCOL" and status == 405):
                return status, b""
            raise BackupError(f"webdav_{method.lower()}_http_{status}") from None
        except (urllib.error.URLError, OSError):
            raise BackupError(f"webdav_{method.lower()}_connection_failed") from None

    def publish(self, snapshot: Path) -> dict[str, object]:
        payload = snapshot.read_bytes()
        if not payload.startswith(b"SQLite format 3\0"):
            raise BackupError("invalid_sqlite_snapshot")
        digest = hashlib.sha256(payload).hexdigest()
        status, current = self.request("GET", limit=len(payload) + 1)
        unchanged = status == 200 and hashlib.sha256(current).hexdigest() == digest
        if not unchanged:
            if status == 404:
                status, _ = self.request("MKCOL", folder=True)
                if status not in (201, 405):
                    raise BackupError("webdav_folder_creation_failed")
            status, _ = self.request(
                "PUT",
                data=payload,
                headers={
                    "Content-Type": "application/octet-stream",
                    "OC-Checksum": "SHA256:" + digest,
                },
            )
            if status not in (200, 201, 204):
                raise BackupError("webdav_put_unexpected_status")
            status, current = self.request("GET", limit=len(payload) + 1)
        if status != 200 or hashlib.sha256(current).hexdigest() != digest:
            raise BackupError("nextcloud_download_verification_failed")
        status, properties = self.request(
            "PROPFIND",
            data=b'<d:propfind xmlns:d="DAV:"><d:prop><d:getcontentlength/></d:prop></d:propfind>',
            headers={"Depth": "0", "Content-Type": "application/xml"},
            limit=1024 * 1024,
        )
        if status != 207:
            raise BackupError("nextcloud_index_verification_failed")
        try:
            declarations = properties.replace(b"\x00", b"").upper()
            if b"<!DOCTYPE" in declarations or b"<!ENTITY" in declarations:
                raise BackupError("invalid_webdav_xml")
            root = ET.fromstring(properties)
            sizes = [
                node.text
                for prop in root.findall(".//{DAV:}propstat")
                if " 200 " in (prop.findtext("{DAV:}status") or "")
                for node in prop.findall("{DAV:}prop/{DAV:}getcontentlength")
            ]
            if not any(int(size or "-1") == len(payload) for size in sizes):
                raise BackupError("nextcloud_index_size_mismatch")
        except (ET.ParseError, ValueError):
            raise BackupError("nextcloud_index_verification_failed") from None
        return {
            "ok": True,
            "path": "RIT/Backups/inventory.sqlite3",
            "sha256Verified": True,
            "indexVerified": True,
            "unchangedUploadSkipped": unchanged,
        }


class InventoryBackup:
    def __init__(self, source: Path, destination: Path) -> None:
        self.source = source
        self.destination = destination

    def write_status(self, report: dict[str, object]) -> None:
        temporary = self.destination / f".status-{uuid4().hex}.tmp"
        try:
            with temporary.open("x") as stream:
                json.dump(report, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.destination / "status.json")
        finally:
            temporary.unlink(missing_ok=True)

    def snapshot(self) -> dict[str, object]:
        if not self.source.is_file():
            raise BackupError("source_missing")
        temporary = self.destination / f".snapshot-{uuid4().hex}.tmp"
        deadline = time.monotonic() + 60

        def progress(*unused) -> None:
            if time.monotonic() > deadline:
                raise BackupError("snapshot_timeout")

        try:
            with closing(sqlite3.connect(self.source.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)) as source:
                with closing(sqlite3.connect(temporary, timeout=10)) as target:
                    source.execute("PRAGMA query_only=ON")
                    source.backup(target, pages=128, progress=progress, sleep=0.05)
                    if target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                        raise BackupError("integrity_failed")
                    tables = {row[0] for row in target.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
                    if not {"inventory_products", "inventory_history"} <= tables:
                        raise BackupError("unexpected_inventory_schema")
            with temporary.open("rb") as stream:
                os.fsync(stream.fileno())
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            temporary.chmod(0o600)
            target_file = self.destination / "inventory.sqlite3"
            temporary.replace(target_file)
            directory_fd = os.open(self.destination, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return {
                "ok": False,
                "snapshotOk": True,
                "integrity": "ok",
                "sourceReadOnly": True,
                "bytes": target_file.stat().st_size,
                "sha256": digest,
                "completedUtc": datetime.now(UTC).isoformat(),
                "nextcloud": {"ok": False},
            }
        finally:
            temporary.unlink(missing_ok=True)

    def run(self) -> dict[str, object]:
        self.destination.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (self.destination / ".backup.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                report = self.snapshot()
                self.write_status(report)
                report["nextcloud"] = NextcloudPublisher().publish(self.destination / "inventory.sqlite3")
                report["ok"] = True
                self.write_status(report)
                return report
            except Exception as error:
                self.write_status(
                    {
                        "ok": False,
                        "errorType": type(error).__name__,
                        "errorCode": str(error) if isinstance(error, BackupError) else "backup_failed",
                        "attemptUtc": datetime.now(UTC).isoformat(),
                    }
                )
                raise


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        print(json.dumps(InventoryBackup(arguments.source, arguments.destination).run()))
    except Exception as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "errorType": type(error).__name__,
                    "errorCode": str(error) if isinstance(error, BackupError) else "backup_failed",
                }
            )
        )
        sys.exit(1)
