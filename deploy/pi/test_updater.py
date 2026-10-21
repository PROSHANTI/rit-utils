"""Exercise actual updater failure/recovery logic without a Docker daemon."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

OLD = "sha256:" + "a" * 64
NEW = "sha256:" + "b" * 64
MANUAL = "sha256:" + "c" * 64
SCRIPT = Path(__file__).with_name("updater.sh")

FAKE_DOCKER = r"""
import json, os, re, sys
from pathlib import Path
path=Path(os.environ["FAKE_DOCKER_STATE"])
s=json.loads(path.read_text())
a=sys.argv[1:]
s["calls"].append(a)
def finish(code=0, out=""):
    path.write_text(json.dumps(s))
    if out: print(out)
    sys.exit(code)
if a == ["version"] or a == ["compose", "version"]: finish()
if a[0] == "pull": finish(0 if s["pull_ok"] else 1)
if a[0] == "inspect":
    if not s["actual"]: finish(1)
    if a[2] == "{{.Image}}": finish(out=s["actual"])
    finish(out="unhealthy" if s["actual"] == s["candidate"] and s["fail_new"] else "healthy")
if a[0] == "exec": finish(1 if s["actual"] == s["candidate"] and s["fail_new"] else 0)
if a[:2] == ["image", "inspect"]:
    if len(a) == 3: finish(0 if a[-1] in s["available"] else 1)
    f=a[3]
    if f == "{{.Id}}": finish(out=s["candidate"])
    if f == "{{.Os}}/{{.Architecture}}": finish(out="linux/arm64")
    if "image.source" in f: finish(out="https://github.com/PROSHANTI/rit-utils")
    if "image.revision" in f: finish(out="d"*40)
    finish(2)
if a[0] == "compose":
    base=Path(os.environ["DEPLOY_DIR"])
    state=Path(os.environ["STATE_DIR"])
    expected=["--env-file", str(base/"deployment.env"), "--project-directory", str(base)]
    assert a[1:7] == expected + ["--project-name", "rit-utils-pi"]
    assert a[7:11] == ["-f", str(base/"compose.yml"), "-f", str(state/"image.yml")]
    assert a[11:] == ["up", "--detach", "--no-deps", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "180", "app"]
    assert not any(x in a for x in ("down", "prune", "rm", "--remove-orphans", "--renew-anon-volumes"))
    image=re.search(r"sha256:[a-f0-9]{64}", (state/"image.yml").read_text()).group(0)
    s["actual"]=image
    s["deployments"].append(image)
    finish(1 if image==s["candidate"] and s["fail_new"] else 0)
finish(2)
"""


def exercise(case: str) -> None:
    with tempfile.TemporaryDirectory(prefix="rit-utils-updater-", dir=SCRIPT.parent) as temporary:
        root = Path(temporary)
        binaries, deploy, state = (root / name for name in ("bin", "deploy", "state"))
        for directory in (binaries, deploy, state):
            directory.mkdir()
        (deploy / "compose.yml").write_text("services: {app: {image: placeholder}}\n")
        (deploy / "deployment.env").write_text("RITUTILS_PRIVATE_DIR=/private-placeholder\n")
        daemon = {
            "actual": OLD,
            "candidate": NEW,
            "pull_ok": case != "failed-pull",
            "fail_new": case == "health-failure",
            "available": [OLD, NEW, MANUAL],
            "calls": [],
            "deployments": [],
        }
        if case in {"pending-recovery", "pending-missing-app"}:
            daemon["actual"] = NEW if case == "pending-recovery" else ""
            (state / "last-good").write_text(OLD + "\n")
            (state / "pending").write_text(OLD + "\n" + NEW + "\n")
        if case == "rejected-digest":
            (state / "last-good").write_text(OLD + "\n")
            (state / "rejected").write_text(NEW + "\n")
        if case == "manual-change":
            daemon["actual"] = MANUAL
            (state / "last-good").write_text(OLD + "\n")
        daemon_file = root / "daemon.json"
        daemon_file.write_text(json.dumps(daemon))
        (binaries / "docker").write_text(f"#!{sys.executable}\n" + FAKE_DOCKER)
        for command in ("sync", "flock", "sleep"):
            (binaries / command).write_text("#!/bin/sh\nexit 0\n")
        for executable in binaries.iterdir():
            executable.chmod(0o700)
        environment = {
            "PATH": f"{binaries}:/usr/bin:/bin",
            "DEPLOY_DIR": str(deploy),
            "STATE_DIR": str(state),
            "FAKE_DOCKER_STATE": str(daemon_file),
            "STABLE_SECONDS": "0",
        }

        result = subprocess.run(["/bin/sh", str(SCRIPT), "--once"], env=environment, capture_output=True, text=True, timeout=20)

        actual = json.loads(daemon_file.read_text())
        assert result.returncode == 0, (case, result.stdout, result.stderr)
        assert all(not any(word in call for word in ("down", "prune", "rm")) for call in actual["calls"])
        if case == "success":
            assert actual["deployments"] == [NEW]
            assert (state / "last-good").read_text().strip() == NEW
            assert not (state / "pending").exists()
        elif case == "health-failure":
            assert actual["deployments"] == [NEW, OLD]
            assert actual["actual"] == OLD
            assert (state / "last-good").read_text().strip() == OLD
            assert NEW in (state / "rejected").read_text()
            assert not (state / "pending").exists()
        elif case in {"pending-recovery", "pending-missing-app"}:
            assert actual["deployments"] == [OLD]
            assert actual["actual"] == OLD
            assert NEW in (state / "rejected").read_text()
            assert not (state / "pending").exists()
        elif case == "manual-change":
            assert not actual["deployments"]
            assert actual["actual"] == MANUAL
            assert (state / "blocked").exists()
        else:
            assert not actual["deployments"]
            assert actual["actual"] == OLD
            assert (state / "last-good").read_text().strip() == OLD


if __name__ == "__main__":
    cases = (
        "failed-pull",
        "success",
        "health-failure",
        "pending-recovery",
        "pending-missing-app",
        "rejected-digest",
        "manual-change",
    )
    for name in cases:
        exercise(name)
        print(f"PASS {name}")
    print(f"PASS {len(cases)} updater scenarios; no real Docker calls")
