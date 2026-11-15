"""Consistent private-instance backups and restores into EMPTY *_restore projects.

Requires Python 3.11+ and Docker Compose. Stop external writers before backup.
The backend and frontend pause while the database and uploaded PDFs are copied.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF_NAME = re.compile(r"[0-9a-f]{32}\.pdf")

PACK = """
import pathlib,re,sys,tarfile
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as archive:
    for path in sorted(pathlib.Path('/data/uploads').iterdir()):
        valid = re.fullmatch(r'[0-9a-f]{32}\\.pdf',path.name)
        if path.is_symlink() or not path.is_file() or not valid:
            raise ValueError('Unexpected upload entry')
        archive.add(path,arcname=path.name,recursive=False)
"""
UNPACK = """
import pathlib,re,shutil,sys,tarfile
root=pathlib.Path('/data/uploads')
if any(root.iterdir()): raise ValueError('Restore upload volume must be empty')
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as archive:
    for member in archive:
        if not member.isfile() or not re.fullmatch(r'[0-9a-f]{32}\\.pdf',member.name):
            raise ValueError('Unsafe archive entry')
        with (root/member.name).open('xb') as target:
            shutil.copyfileobj(archive.extractfile(member),target)
"""


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_archive(path):
    names = set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            if not member.isfile() or not PDF_NAME.fullmatch(member.name) or member.name in names:
                raise ValueError("Unsafe or duplicate upload archive member")
            names.add(member.name)
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--env-file", default="deploy/vps.env")
    parser.add_argument("--compose-file", action="append")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", args.project):
        parser.error("Invalid Compose project name")
    docker = shutil.which("docker") or "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
    command = [docker, "compose", "--env-file", str(ROOT / args.env_file), "-p", args.project]
    for name in args.compose_file or ["docker-compose.yml", "compose.vps.yml"]:
        command += ["-f", str(ROOT / name)]

    def run(*items, **kwargs):
        return subprocess.run([*command, *items], cwd=ROOT, check=True, **kwargs)

    directory = args.directory.resolve()
    if args.action == "backup":
        directory.mkdir(parents=True, exist_ok=False)
        directory.chmod(0o700)
        services = run(
            "ps", "--status", "running", "--services", capture_output=True, text=True
        ).stdout.split()
        restart = [name for name in ("frontend", "backend") if name in services]
        try:
            if restart:
                run("stop", "-t", "180", *restart)
            with (directory / "db.dump").open("xb") as output:
                run(
                    "exec",
                    "-T",
                    "db",
                    "pg_dump",
                    "-U",
                    "scholargraph",
                    "-d",
                    "scholargraph",
                    "-Fc",
                    "--no-owner",
                    stdout=output,
                )
            with (directory / "uploads.tar.gz").open("xb") as output:
                run(
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "--entrypoint",
                    "python",
                    "backend",
                    "-c",
                    PACK,
                    stdout=output,
                )
            count = len(validate_archive(directory / "uploads.tar.gz"))
            manifest = {
                "version": 1,
                "created_utc": datetime.now(UTC).isoformat(),
                "upload_count": count,
                "sha256": {
                    name: digest(directory / name) for name in ("db.dump", "uploads.tar.gz")
                },
            }
            (directory / "manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
        finally:
            if restart:
                run("start", *reversed(restart))
        print(f"Backup complete: {directory} ({count} PDFs). Copy encrypted backups off-host.")
    else:
        if not args.project.endswith("_restore"):
            parser.error("Restore requires a separate project ending in _restore")
        manifest = json.loads((directory / "manifest.json").read_text())
        if manifest["version"] != 1:
            raise ValueError("Unsupported backup format")
        for name in ("db.dump", "uploads.tar.gz"):
            if digest(directory / name) != manifest["sha256"][name]:
                raise ValueError("Backup checksum mismatch")
        if len(validate_archive(directory / "uploads.tar.gz")) != manifest["upload_count"]:
            raise ValueError("Backup upload count mismatch")
        run("up", "-d", "--wait", "db")
        count = run(
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "scholargraph",
            "-d",
            "scholargraph",
            "-Atc",
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",
            capture_output=True,
            text=True,
        ).stdout.strip()
        if count != "0":
            raise ValueError("Restore database must be empty; no existing tables are overwritten")
        run(
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "--entrypoint",
            "python",
            "backend",
            "-c",
            "from pathlib import Path; assert not any(Path('/data/uploads').iterdir()), "
            "'Restore upload volume must be empty'",
        )
        with (directory / "db.dump").open("rb") as source:
            run(
                "exec",
                "-T",
                "db",
                "pg_restore",
                "-U",
                "scholargraph",
                "-d",
                "scholargraph",
                "--no-owner",
                "--exit-on-error",
                stdin=source,
            )
        with (directory / "uploads.tar.gz").open("rb") as source:
            run(
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "--entrypoint",
                "python",
                "backend",
                "-c",
                UNPACK,
                stdin=source,
            )
        print("Restore complete in isolated project. Verify data before starting the application.")


if __name__ == "__main__":
    main()
