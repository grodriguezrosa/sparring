"""Pre-publish checks: everything that must pass before a branch is pushed to GitHub.

Usage:
    make preflight      check the checked-out branch by hand
    make hooks          install the pre-push hook, so every `git push` runs these checks

Emergency skip (it is still checked by CI): git push --no-verify
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

ZERO_SHA = "0" * 40
GIT = shutil.which("git") or "git"

# Branches that only change through a pull request, so CI runs before the merge.
PROTECTED_BRANCHES = frozenset({"master", "main"})
LONG_LIVED_BRANCHES = frozenset({"develop"})
BRANCH_NAME = re.compile(r"^(feature|fix|docs|chore|refactor|test|spike)/[a-z0-9][a-z0-9._-]*$")

# Files that must never reach the remote: keys and personal learning material.
FORBIDDEN_PATHS = (
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)\.env\.(?!example$)[^/]+$"),  # .env.local, .env.prod... but not .env.example
    re.compile(r"^(lessons|spikes)/"),  # personal, git-excluded material
    re.compile(r"(^|/)CLAUDE\.local\.md$"),
    re.compile(r"\.(pem|key|p12|pfx)$"),
)

# Well-known key formats. Matches are reported by kind and place, never by value.
SECRET_PATTERNS = {
    "OpenAI-style key (DeepSeek)": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "ElevenLabs key": re.compile(r"\bsk_[A-Za-z0-9]{32,}"),
    "Vercel AI Gateway key": re.compile(r"\bvck_[A-Za-z0-9]{20,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "database URL with a password": re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^:/\s]+:[^@/\s]+@"),
}

# .env variables whose values are secrets, and the shortest value worth looking for
# (shorter ones would match by chance).
SECRET_ENV_NAME = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|CODE")
MIN_SECRET_LENGTH = 12

MAX_FILE_BYTES = 1_000_000

SLOW_CHECKS = (
    ("uv.lock in sync with pyproject.toml", ["uv", "lock", "--check"]),
    ("lint, types and tests (make check)", ["make", "check"]),
)


@dataclass(frozen=True)
class PushedRef:
    """One line of what git sends to the pre-push hook on stdin."""

    local_ref: str
    local_sha: str
    remote_ref: str
    remote_sha: str

    @property
    def is_deletion(self) -> bool:
        return self.local_sha == ZERO_SHA

    @property
    def branch(self) -> str | None:
        prefix = "refs/heads/"
        if not self.remote_ref.startswith(prefix):
            return None  # a tag, for example
        return self.remote_ref.removeprefix(prefix)


def parse_pre_push_input(text: str) -> list[PushedRef]:
    """Each line is `<local ref> <local sha> <remote ref> <remote sha>`."""
    return [PushedRef(*line.split()) for line in text.splitlines() if line.strip()]


def check_branch_name(branch: str, *, allow_protected: bool) -> list[str]:
    if branch in PROTECTED_BRANCHES:
        if allow_protected:
            return []
        return [
            f"direct push to '{branch}': merge it through a pull request so CI runs first "
            "(override once with ALLOW_PROTECTED_PUSH=1 git push)"
        ]
    if branch in LONG_LIVED_BRANCHES or BRANCH_NAME.match(branch):
        return []
    return [
        f"branch name '{branch}' does not follow <type>/<lowercase-name>, "
        "with type one of feature, fix, docs, chore, refactor, test, spike"
    ]


def find_forbidden_paths(paths: Iterable[str]) -> list[str]:
    return sorted(p for p in set(paths) if any(rule.search(p) for rule in FORBIDDEN_PATHS))


def find_large_files(ls_tree_output: str) -> list[str]:
    """Parse `git ls-tree -r -l`: `<mode> <type> <sha> <size>\\t<path>` per line."""
    problems = []
    for line in ls_tree_output.splitlines():
        meta, _, path = line.partition("\t")
        size = meta.split()[-1]
        if size.isdigit() and int(size) > MAX_FILE_BYTES:
            problems.append(f"{path} is {int(size) / 1_000_000:.1f} MB (limit 1 MB)")
    return problems


def read_env_secrets(env_file: Path) -> dict[str, str]:
    """Map each secret value in .env to its variable name. Values are never printed."""
    if not env_file.is_file():
        return {}
    secrets: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, sep, raw_value = line.strip().partition("=")
        if not sep or name.startswith("#") or not SECRET_ENV_NAME.search(name):
            continue
        for value in raw_value.strip().strip("\"'").split(","):
            if len(value.strip()) >= MIN_SECRET_LENGTH:
                secrets[value.strip()] = name
    return secrets


def find_secrets_in_patch(patch: str, known_secrets: Mapping[str, str]) -> list[str]:
    """Look for secrets in the lines ADDED by a `git log -p --format='commit %h'` patch.

    Every commit is scanned, not just the final state: a key added and removed in a
    later commit still travels to GitHub inside the history.
    """
    findings: list[str] = []
    commit, path = "?", "?"
    for line in patch.splitlines():
        if line.startswith("commit "):
            commit = line.removeprefix("commit ")
        elif line.startswith("+++ "):
            path = line.removeprefix("+++ ").removeprefix("b/")
        elif line.startswith("+"):
            added = line[1:]
            for kind, pattern in SECRET_PATTERNS.items():
                if pattern.search(added):
                    findings.append(f"{commit} {path}: looks like a {kind}")
            for value, name in known_secrets.items():
                if value in added:
                    findings.append(f"{commit} {path}: contains the value of {name} from .env")
    return list(dict.fromkeys(findings))  # remove duplicates, keep order


def git(*args: str) -> str:
    result = subprocess.run([GIT, *args], capture_output=True, text=True, check=True)  # noqa: S603  (fixed git commands, no shell)
    return result.stdout


def check_ref(
    ref: PushedRef, *, known_secrets: Mapping[str, str], allow_protected: bool
) -> list[str]:
    failures: list[str] = []
    if ref.branch is not None:
        failures += check_branch_name(ref.branch, allow_protected=allow_protected)

    # Commits reachable from the pushed commit that no remote has yet.
    not_on_remote = [ref.local_sha, "--not", "--remotes"]
    touched = git("log", "--format=", "--name-only", *not_on_remote).splitlines()
    final_tree = git("ls-tree", "-r", "--name-only", ref.local_sha).splitlines()
    for path in find_forbidden_paths(p for p in [*touched, *final_tree] if p):
        failures.append(f"forbidden file in the push: {path}")

    failures += find_large_files(git("ls-tree", "-r", "-l", ref.local_sha))

    patch = git(
        "log", "-p", "-U0", "--no-color", "--no-ext-diff", "--format=commit %h", *not_on_remote
    )
    failures += find_secrets_in_patch(patch, known_secrets)
    return failures


def run_fast_checks(
    refs: Sequence[PushedRef], *, env_file: Path, allow_dirty: bool, allow_protected: bool
) -> list[str]:
    failures: list[str] = []
    head = git("rev-parse", "HEAD").strip()
    known_secrets = read_env_secrets(env_file)
    for ref in refs:
        if ref.is_deletion:
            continue
        if ref.local_sha != head:
            failures.append(
                f"{ref.local_ref} is not the checked-out commit, so the tests would run against "
                "other code: check it out and push again"
            )
        failures += check_ref(ref, known_secrets=known_secrets, allow_protected=allow_protected)
    if not allow_dirty and git("status", "--porcelain").strip():
        failures.append(
            "uncommitted or untracked files: the tests would see code that is not being pushed "
            "(commit or stash them; see `git status`)"
        )
    return list(dict.fromkeys(failures))


def current_branch_ref() -> PushedRef:
    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    sha = git("rev-parse", "HEAD").strip()
    return PushedRef(f"refs/heads/{branch}", sha, f"refs/heads/{branch}", ZERO_SHA)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Checks to pass before pushing a branch.")
    parser.add_argument(
        "--pre-push", action="store_true", help="read pushed refs from stdin (git hook)"
    )
    parser.add_argument(
        "--allow-dirty", action="store_true", help="do not require a clean working tree"
    )
    parser.add_argument("--live", action="store_true", help="also run the live tests (costs money)")
    args = parser.parse_args(argv)

    refs = parse_pre_push_input(sys.stdin.read()) if args.pre_push else [current_branch_ref()]
    if all(ref.is_deletion for ref in refs):
        return 0  # nothing new is being published

    print("Preflight: fast checks (branch, forbidden files, secrets, clean tree)...")
    failures = run_fast_checks(
        refs,
        env_file=Path(".env"),
        allow_dirty=args.allow_dirty,
        allow_protected=os.environ.get("ALLOW_PROTECTED_PUSH") == "1",
    )
    if failures:
        print("\nPreflight FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("  ok")

    slow_checks = [*SLOW_CHECKS]
    if args.live:
        slow_checks.append(("live tests against the real APIs", ["make", "test-live"]))
    for name, command in slow_checks:
        print(f"Preflight: {name}...")
        if subprocess.run(command, check=False).returncode != 0:  # noqa: S603  (fixed commands)
            print(f"\nPreflight FAILED: {name}")
            return 1

    print("\nPreflight passed: the branch is ready to publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
