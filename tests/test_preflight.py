import subprocess
from pathlib import Path

import pytest

from scripts.preflight import (
    ZERO_SHA,
    PushedRef,
    check_branch_name,
    find_forbidden_paths,
    find_large_files,
    find_secrets_in_patch,
    parse_pre_push_input,
    read_env_secrets,
    run_fast_checks,
)

# Fake secrets are built in pieces so this file itself never looks like it leaks one.
FAKE_DEEPSEEK_KEY = "sk-" + "a1" * 16
FAKE_ENV_VALUE = "my-real-" + "access-code-123"
SHA = "1" * 40


def test_parses_pre_push_input() -> None:
    text = f"refs/heads/feature/x {SHA} refs/heads/feature/x {ZERO_SHA}\n"

    (ref,) = parse_pre_push_input(text)

    assert ref.branch == "feature/x"
    assert not ref.is_deletion


def test_detects_deletions_and_tags() -> None:
    deletion, tag = parse_pre_push_input(
        f"(delete) {ZERO_SHA} refs/heads/old {SHA}\nrefs/tags/v1 {SHA} refs/tags/v1 {ZERO_SHA}\n"
    )

    assert deletion.is_deletion
    assert tag.branch is None


@pytest.mark.parametrize(
    "branch", ["feature/interview-plan", "fix/quota-reset", "spike/jev", "docs/readme", "develop"]
)
def test_accepts_valid_branch_names(branch: str) -> None:
    assert check_branch_name(branch, allow_protected=False) == []


@pytest.mark.parametrize("branch", ["my-branch", "Feature/Plan", "feature/", "wip/stuff"])
def test_rejects_invalid_branch_names(branch: str) -> None:
    assert check_branch_name(branch, allow_protected=False) != []


def test_blocks_direct_push_to_master_unless_allowed() -> None:
    assert "pull request" in check_branch_name("master", allow_protected=False)[0]
    assert check_branch_name("master", allow_protected=True) == []


def test_finds_forbidden_paths() -> None:
    paths = [
        ".env",
        "deploy/.env",
        ".env.local",
        ".env.example",
        "lessons/01-harness.md",
        "spikes/001-jev/decide.py",
        "CLAUDE.local.md",
        "certs/server.pem",
        "app/main.py",
        "app/api/security.py",
    ]

    assert find_forbidden_paths(paths) == [
        ".env",
        ".env.local",
        "CLAUDE.local.md",
        "certs/server.pem",
        "deploy/.env",
        "lessons/01-harness.md",
        "spikes/001-jev/decide.py",
    ]


def test_finds_large_files() -> None:
    ls_tree = (
        "100644 blob abc     120\tapp/main.py\n100644 blob def 2500000\tdata/dump.sql\n"
        "160000 commit fed       -\tvendor/lib\n"
    )

    assert find_large_files(ls_tree) == ["data/dump.sql is 2.5 MB (limit 1 MB)"]


def test_reads_secret_values_from_env_file(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        f'DEEPSEEK_API_KEY="{FAKE_DEEPSEEK_KEY}"\n'
        f"ACCESS_CODES={FAKE_ENV_VALUE}, second-code-456789\n"
        "ELEVENLABS_AGENT_ID=agent_not_a_secret_123\n"
        "SHORT_KEY=abc\n",
        encoding="utf-8",
    )

    assert read_env_secrets(env) == {
        FAKE_DEEPSEEK_KEY: "DEEPSEEK_API_KEY",
        FAKE_ENV_VALUE: "ACCESS_CODES",
        "second-code-456789": "ACCESS_CODES",
    }


def test_missing_env_file_means_no_known_secrets(tmp_path: Path) -> None:
    assert read_env_secrets(tmp_path / ".env") == {}


def test_finds_secrets_only_in_added_lines_and_never_prints_them() -> None:
    patch = (
        "commit abc1234\n"
        "+++ b/app/config.py\n"
        f'+api_key = "{FAKE_DEEPSEEK_KEY}"\n'
        f'-old = "{FAKE_ENV_VALUE}"\n'
        "+++ b/README.md\n"
        f"+Use the code {FAKE_ENV_VALUE}\n"
    )

    findings = find_secrets_in_patch(patch, {FAKE_ENV_VALUE: "ACCESS_CODES"})

    assert findings == [
        "abc1234 app/config.py: looks like a OpenAI-style key (DeepSeek)",
        "abc1234 README.md: contains the value of ACCESS_CODES from .env",
    ]
    assert not any(FAKE_DEEPSEEK_KEY in f or FAKE_ENV_VALUE in f for f in findings)


def _git(repo: Path, *args: str) -> str:
    command = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args]
    result = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=True)  # noqa: S603  (fixed git commands)
    return result.stdout


def test_a_secret_removed_in_a_later_commit_is_still_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(tmp_path, "init", "--quiet", "--initial-branch=feature/leak")
    (tmp_path / "settings.py").write_text(f'KEY = "{FAKE_DEEPSEEK_KEY}"\n', encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "Add settings")
    (tmp_path / "settings.py").write_text('KEY = ""\n', encoding="utf-8")
    _git(tmp_path, "commit", "--quiet", "-am", "Remove the key")
    head = _git(tmp_path, "rev-parse", "HEAD").strip()
    monkeypatch.chdir(tmp_path)
    ref = PushedRef("refs/heads/feature/leak", head, "refs/heads/feature/leak", ZERO_SHA)

    failures = run_fast_checks(
        [ref], env_file=tmp_path / ".env", allow_dirty=False, allow_protected=False
    )

    assert len(failures) == 1
    assert "settings.py: looks like a OpenAI-style key" in failures[0]


def test_a_clean_branch_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _git(tmp_path, "init", "--quiet", "--initial-branch=feature/clean")
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "Add main")
    head = _git(tmp_path, "rev-parse", "HEAD").strip()
    monkeypatch.chdir(tmp_path)
    ref = PushedRef("refs/heads/feature/clean", head, "refs/heads/feature/clean", ZERO_SHA)

    assert (
        run_fast_checks([ref], env_file=Path(".env"), allow_dirty=False, allow_protected=False)
        == []
    )


def test_untracked_files_fail_unless_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(tmp_path, "init", "--quiet", "--initial-branch=feature/wip")
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "Add main")
    (tmp_path / "conftest.py").write_text("\n", encoding="utf-8")
    head = _git(tmp_path, "rev-parse", "HEAD").strip()
    monkeypatch.chdir(tmp_path)
    ref = PushedRef("refs/heads/feature/wip", head, "refs/heads/feature/wip", ZERO_SHA)

    strict = run_fast_checks([ref], env_file=Path(".env"), allow_dirty=False, allow_protected=False)
    relaxed = run_fast_checks([ref], env_file=Path(".env"), allow_dirty=True, allow_protected=False)

    assert "uncommitted or untracked files" in strict[0]
    assert relaxed == []
