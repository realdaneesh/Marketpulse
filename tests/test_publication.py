"""Publication tooling uses temporary files, never an operator's database or Git history."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from scripts.audit_publication import audit, inspect_bytes
from scripts.initialize_database import initialize


async def test_initializer_creates_schema_three_and_refuses_existing_file(tmp_path):
    path = tmp_path / "new" / "fresh.sqlite3"
    await initialize(path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert db.execute("SELECT count(*) FROM trades").fetchone()[0] == 0
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        await initialize(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_candidate_audit_uses_actual_ignore_rules_without_creating_repository(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / ".gitignore").write_bytes((root / ".gitignore").read_bytes())
    allowed = (
        "README.md",
        ".env.example",
        "frontend/.env.example",
        "frontend/src/test/fixture.json",
    )
    excluded = (
        ".env",
        "frontend/.env.local",
        "data/export.json",
        "capture.sqlite3-wal",
        "backup.db",
        ".venv/secret.txt",
        "frontend/node_modules/module.js",
        "frontend/dist/bundle.js",
        ".vscode/settings.json",
        "signing.pem",
    )
    for name in (*allowed, *excluded):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic fixture", encoding="utf-8")
    result = audit(tmp_path)
    assert result["passed"]
    assert set(result["candidates"]) == {".gitignore", *allowed}
    assert result["git"]["initialized"] is False
    assert result["git"]["commits"] == result["git"]["tracked_files"] == 0
    assert not (tmp_path / ".git").exists()


def test_sensitive_findings_report_locations_without_exposing_values():
    credential = "synthetic" + "-credential-123456789"
    token = "ghp_" + "a" * 40
    personal = chr(67) + ":/" + "Users" + "/private-operator/file"
    label = "pass" + "word"
    payload = f'{label} = "{credential}"\n{token}\n{personal}'
    findings = inspect_bytes("example.txt", payload.encode())
    assert {f["kind"] for f in findings} >= {
        "github_token",
        "potential_credential_assignment",
        "absolute_personal_path",
    }
    report = json.dumps(findings)
    assert not any(value in report for value in (credential, token, personal))
