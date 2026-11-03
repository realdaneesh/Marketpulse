"""Audit Git publishing candidates without staging, committing, or printing secrets.

With no repository, temporary Git metadata applies the actual .gitignore rules.
Existing tracked files/history are also inspected when a repository is present.
This is a conservative pattern audit, not a guarantee that no secret exists.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

PATTERNS = {
    "private_key": r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----",
    "github_token": r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b",
    "aws_access_key": r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "service_token": r"\b(?:xox[baprs]-[A-Za-z0-9-]{20,}|npm_[A-Za-z0-9]{30,})\b",
    "api_token": r"\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}\b",
    "credential_url": r"https?://[^\s/]+:[^\s/@]+@",
    "absolute_personal_path": r"(?i)(?:\b[A-Z]:[\\/]|/(?:Users|home)/[^\s/]+)",
    "jwt": r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
}
ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|passwd|secret)"
    r"\b[\"']?\s*[:=]\s*[\"']([^\"'\r\n]{8,})[\"']"
)
SAFE_VALUE = re.compile(r"(?i)(?:placeholder|example|your[-_ ]|test|dummy|changeme|not[-_ ]real)")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".ico"}
FORBIDDEN_PARTS = {
    "data",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".ruff_cache",
    ".vscode",
    ".idea",
    ".aws",
    ".azure",
    ".ssh",
    ".codex",
    ".agents",
    "dist",
    "build",
    "test-results",
    "playwright-report",
    "coverage",
}
FORBIDDEN_SUFFIX = re.compile(
    r"(?i)(?:\.(?:sqlite3?|db)(?:[-.].*)?|-(?:wal|shm)|\.(?:log|pem|key|p12|pfx|bak|backup|snapshot|dump|sql|zip|whl|tmp|tsbuildinfo))$"
)


def git(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        env=dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull),
        check=False,
    )


def candidates(root: Path) -> tuple[list[str], dict]:
    present = git(["rev-parse", "--show-toplevel"], root)
    initialized = present.returncode == 0
    if initialized and Path(os.fsdecode(present.stdout).strip()).resolve() != root:
        raise RuntimeError("Project is inside another repository; inspect its boundaries manually")
    state = dict(
        initialized=initialized,
        branch=None,
        remotes=0,
        tracked_files=0,
        commits=0,
        history_objects_scanned=0,
    )
    if initialized:
        state["branch"] = os.fsdecode(git(["branch", "--show-current"], root).stdout).strip()
        state["remotes"] = len(git(["remote"], root).stdout.splitlines())
        state["tracked_files"] = sum(
            bool(p) for p in git(["ls-files", "-z"], root).stdout.split(b"\0")
        )
        commits = git(["rev-list", "--all", "--count"], root)
        state["commits"] = int(commits.stdout.strip() or b"0")
        result = git(["ls-files", "--cached", "--others", "--exclude-standard", "-z"], root)
    else:
        with TemporaryDirectory(prefix="marketpulse-publication-git-") as directory:
            temporary = Path(directory)
            if git(["init", "--quiet", "--initial-branch=main", str(temporary)], root).returncode:
                raise RuntimeError("Temporary Git initialization failed")
            result = git(
                [
                    f"--git-dir={temporary / '.git'}",
                    f"--work-tree={root}",
                    "ls-files",
                    "--others",
                    "--exclude-standard",
                    "-z",
                ],
                root,
            )
    if result.returncode:
        raise RuntimeError("Git candidate enumeration failed")
    return sorted(set(os.fsdecode(p) for p in result.stdout.split(b"\0") if p)), state


def forbidden(name: str) -> bool:
    path = Path(name)
    return (
        bool(FORBIDDEN_PARTS.intersection(path.parts))
        or (path.name.startswith(".env") and path.name != ".env.example")
        or bool(FORBIDDEN_SUFFIX.search(name))
        or path.name in {".npmrc", ".pypirc", ".netrc", "credentials.json"}
    )


def inspect_bytes(name: str, payload: bytes) -> list[dict]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        return (
            []
            if Path(name).suffix.lower() in IMAGE_SUFFIXES
            else [dict(path=name, kind="unreviewed_binary")]
        )
    issues = []
    for kind, pattern in PATTERNS.items():
        for match in re.finditer(pattern, text):
            issues.append(dict(path=name, kind=kind, line=text.count("\n", 0, match.start()) + 1))
    for match in ASSIGNMENT.finditer(text):
        if not SAFE_VALUE.search(match.group(1)):
            issues.append(
                dict(
                    path=name,
                    kind="potential_credential_assignment",
                    line=text.count("\n", 0, match.start()) + 1,
                )
            )
    return issues


def history(root: Path, state: dict) -> list[dict]:
    if not state["initialized"]:
        return []
    objects = git(["rev-list", "--objects", "--all"], root)
    if objects.returncode:
        raise RuntimeError("Cannot enumerate history")
    issues = []
    for record in objects.stdout.splitlines():
        oid, _, raw_name = record.partition(b" ")
        object_id = oid.decode("ascii")
        name = os.fsdecode(raw_name) if raw_name else "<commit-or-tag>"
        kind = git(["cat-file", "-t", object_id], root).stdout.strip()
        if kind not in (b"blob", b"commit", b"tag"):
            continue
        size = int(git(["cat-file", "-s", object_id], root).stdout)
        state["history_objects_scanned"] += 1
        if forbidden(name) or size > 5 * 1024 * 1024:
            issues.append(
                dict(path=name, kind="history_private_or_large_artifact", object=object_id[:12])
            )
        if size <= 5 * 1024 * 1024:
            for issue in inspect_bytes(name, git(["cat-file", "-p", object_id], root).stdout):
                issues.append(dict(**issue, object=object_id[:12]))
    return issues


def audit(root: Path) -> dict:
    names, state = candidates(root)
    issues, sizes = [], []
    for name in names:
        path = root / name
        if path.is_symlink():
            issues.append(dict(path=name, kind="symlink_requires_review"))
            continue
        if not path.is_file():
            issues.append(dict(path=name, kind="missing_tracked_file"))
            continue
        size = path.stat().st_size
        sizes.append(dict(path=name, bytes=size))
        if forbidden(name):
            issues.append(dict(path=name, kind="private_or_generated_candidate"))
        if size > 5 * 1024 * 1024:
            issues.append(dict(path=name, kind="oversized_candidate", bytes=size))
            continue
        issues.extend(inspect_bytes(name, path.read_bytes()))
    issues.extend(history(root, state))
    return dict(
        git=state,
        candidate_count=len(names),
        total_bytes=sum(p["bytes"] for p in sizes),
        candidates=names,
        largest_files=sorted(sizes, key=lambda p: p["bytes"], reverse=True)[:10],
        findings=issues,
        passed=not issues,
        limitation="Pattern audit plus manual review; never a guarantee of secret absence.",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--export", type=Path, help="Copy reviewed candidates to a new empty directory"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = audit(root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "candidates"}, indent=2))
    if not result["passed"]:
        raise SystemExit(
            "Publication audit has findings; no export performed. Values are redacted."
        )
    if args.export:
        destination = args.export.resolve()
        destination.mkdir(parents=True, exist_ok=False)
        for name in result["candidates"]:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, target)
        print(f"Exported {result['candidate_count']} reviewed files to a new directory")


if __name__ == "__main__":
    main()
