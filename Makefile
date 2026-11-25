# Project shortcuts. Usage: make <target>   (for example: make check)
.PHONY: install dev lint format typecheck test test-live check preflight hooks tunnel agent-config interview voice-dev voice-interview latency

install:  ## Install the exact dependencies from uv.lock
	uv sync

dev:  ## Start the development server with auto-reload
	uv run fastapi dev app/main.py

lint:  ## Look for errors and check formatting (changes nothing)
	uv run ruff check .
	uv run ruff format --check .

format:  ## Apply ruff's automatic fixes, then format (fixes can leave code unformatted)
	# --fix-only: exit 0 even if unfixable errors remain, so the formatter still runs
	uv run ruff check --fix-only .
	uv run ruff format .

typecheck:  ## Type-check with mypy (strict mode)
	uv run mypy

test:  ## Run the tests (without the live ones)
	uv run pytest

test-live:  ## Run only the tests that call real APIs (needs .env, costs money)
	uv run pytest -m live -s

check: lint typecheck test  ## Everything that must pass before considering something done

preflight:  ## Pre-publish checks for the checked-out branch (the pre-push hook runs the same)
	uv run python scripts/preflight.py

hooks:  ## Install the git hooks in .githooks/ (pre-push runs the preflight checks)
	git config core.hooksPath .githooks

# --- Voice interview in development (ADR 0002) ---------------------------------------

tunnel:  ## Public https URL for `make dev` (prints a new trycloudflare.com URL every time)
	cloudflared tunnel --no-autoupdate --url http://localhost:8000

agent-config:  ## Point the ElevenLabs agent at the tunnel: make agent-config URL=https://...
	@test -n "$(URL)" || (echo "Usage: make agent-config URL=https://xxx.trycloudflare.com" && exit 1)
	uv run python -m scripts.configure_agent --llm-url $(URL)

interview:  ## Typed interview through the real agent (uses 1 conversation of the daily limit)
	uv run python -m scripts.text_interview

voice-dev:  ## Backend + tunnel + agent config, auto-stops (default 30 min): make voice-dev MINUTES=45
	uv run python -m scripts.dev_session --minutes $(or $(MINUTES),30)

voice-interview:  ## Spoken interview (needs `make voice-dev` running; headphones): PLAN=backups/last-plan.json
	uv run python -m scripts.voice_interview $(if $(PLAN),--plan $(PLAN))

latency:  ## Per-turn latency of the agent's last conversations
	uv run python -m scripts.latency_report
