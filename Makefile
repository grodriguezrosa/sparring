# Project shortcuts. Usage: make <target>   (for example: make check)
.PHONY: install dev lint format typecheck test test-live check preflight hooks

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
