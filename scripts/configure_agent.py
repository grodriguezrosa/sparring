"""Point the ElevenLabs agent at our custom LLM endpoint (ADR 0002).

Usage:
    make tunnel                                   # terminal 1, with `make dev` running
    make agent-config URL=https://xxx.trycloudflare.com
    uv run python -m scripts.configure_agent --llm-url URL --dry-run
    uv run python -m scripts.configure_agent --restore backups/agent-....json

Before changing anything it saves the current agent to backups/ (git-ignored). Only the
fields in MANAGED_FIELDS are changed, and afterwards it checks that the limits, voice,
duration and tools are still the same.
"""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings, get_settings
from app.services.interviewer import AGENT_FIRST_MESSAGE, AGENT_PROMPT_STUB

SECRET_NAME = "sparring-agent-llm-secret"  # noqa: S105  (the name of the secret, not its value)
MODEL_ID = "sparring-interviewer"
BACKUP_DIR = Path("backups")

# The only fields this script writes (dotted paths inside the agent JSON).
MANAGED_FIELDS = (
    "conversation_config.agent.first_message",
    "conversation_config.agent.prompt.prompt",
    "conversation_config.agent.prompt.llm",
    "conversation_config.agent.prompt.custom_llm",
    "platform_settings.auth.enable_auth",
    "platform_settings.overrides.conversation_config_override.conversation.text_only",
)
# Fields that must survive the update untouched.
PRESERVED_FIELDS = (
    "conversation_config.agent.language",
    "conversation_config.tts.voice_id",
    "conversation_config.tts.model_id",
    "conversation_config.conversation.max_duration_seconds",
    "conversation_config.agent.prompt.built_in_tools",
    "platform_settings.call_limits",
)


def dig(data: Mapping[str, Any], path: str) -> Any:
    """Read a dotted path such as 'a.b.c' from nested dicts; None if any part is missing."""
    value: Any = data
    for key in path.split("."):
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    return value


def nest(values: Mapping[str, Any]) -> dict[str, Any]:
    """Turn {'a.b': 1, 'a.c': 2} into {'a': {'b': 1, 'c': 2}} (the shape PATCH expects)."""
    result: dict[str, Any] = {}
    for path, value in values.items():
        *parents, leaf = path.split(".")
        node = result
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = value
    return result


def validate_llm_url(url: str) -> str:
    """The public base URL of our backend (https, no path). ElevenLabs appends the rest."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/"):
        raise ValueError(
            "--llm-url must be an https base URL such as https://xxx.trycloudflare.com"
        )
    return f"https://{parsed.netloc}"


def desired_values(llm_url: str, secret_id: str) -> dict[str, Any]:
    return {
        "conversation_config.agent.first_message": AGENT_FIRST_MESSAGE,
        "conversation_config.agent.prompt.prompt": AGENT_PROMPT_STUB,
        "conversation_config.agent.prompt.llm": "custom-llm",
        "conversation_config.agent.prompt.custom_llm": {
            # ElevenLabs appends /chat/completions (verified in the ADR 0002 spike).
            "url": f"{validate_llm_url(llm_url)}/v1",
            "model_id": MODEL_ID,
            "api_key": {"secret_id": secret_id},
        },
        "platform_settings.auth.enable_auth": True,  # only signed URLs can start a conversation
        "platform_settings.overrides.conversation_config_override.conversation.text_only": False,
    }


def check_update(
    before: Mapping[str, Any], after: Mapping[str, Any], desired: Mapping[str, Any]
) -> list[str]:
    """Problems after the update: managed fields not applied, or preserved fields changed."""
    problems = []
    for path, value in desired.items():
        actual = dig(after, path)
        if path.endswith("custom_llm"):
            actual = {k: actual.get(k) for k in ("url", "model_id")} if actual else None
            value = {k: value[k] for k in ("url", "model_id")}
        if actual != value:
            problems.append(f"not applied: {path}")
    problems += [f"changed: {p}" for p in PRESERVED_FIELDS if dig(before, p) != dig(after, p)]
    return problems


def ensure_secret(http: httpx.Client, settings: Settings) -> str:
    """Create or update the workspace secret ElevenLabs sends to our endpoint. Returns its id."""
    value = settings.agent_llm_secret.get_secret_value()
    listing = http.get("/v1/convai/secrets", params={"search": SECRET_NAME})
    listing.raise_for_status()
    existing = [s for s in listing.json()["secrets"] if s["name"] == SECRET_NAME]
    if existing:
        secret_id: str = existing[0]["secret_id"]
        body = {"type": "update", "name": SECRET_NAME, "value": value}
        http.patch(f"/v1/convai/secrets/{secret_id}", json=body).raise_for_status()
        return secret_id
    created = http.post(
        "/v1/convai/secrets", json={"type": "new", "name": SECRET_NAME, "value": value}
    )
    created.raise_for_status()
    new_id: str = created.json()["secret_id"]
    return new_id


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Point the ElevenLabs agent at our backend.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--llm-url", help="public https base URL of the backend (tunnel)")
    group.add_argument(
        "--restore", type=Path, help="backup file to restore the managed fields from"
    )
    parser.add_argument("--dry-run", action="store_true", help="show the update, change nothing")
    args = parser.parse_args(argv)

    settings = get_settings()
    agent_path = f"/v1/convai/agents/{settings.elevenlabs_agent_id}"
    headers = {"xi-api-key": settings.elevenlabs_api_key.get_secret_value()}
    with httpx.Client(base_url=settings.elevenlabs_base_url, headers=headers, timeout=30) as http:
        before = http.get(agent_path)
        before.raise_for_status()
        current: dict[str, Any] = before.json()

        if args.restore:
            backup = json.loads(args.restore.read_text(encoding="utf-8"))
            desired = {path: dig(backup, path) for path in MANAGED_FIELDS}
        else:
            secret_id = "<created on apply>" if args.dry_run else ensure_secret(http, settings)
            desired = desired_values(args.llm_url, secret_id)

        if args.dry_run:
            print(json.dumps(nest(desired), ensure_ascii=False, indent=2))
            return 0

        BACKUP_DIR.mkdir(exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_file = BACKUP_DIR / f"agent-{settings.elevenlabs_agent_id}-{stamp}.json"
        backup_file.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Backup of the current agent: {backup_file}")

        response = http.patch(agent_path, json=nest(desired))
        if response.is_error:
            print(f"Update failed: HTTP {response.status_code}: {response.text[:500]}")
            return 1
        after = http.get(agent_path)
        after.raise_for_status()

    problems = check_update(current, after.json(), desired)
    for problem in problems:
        print(f"  - {problem}")
    print("Agent updated." if not problems else "Agent updated WITH PROBLEMS (see above).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
