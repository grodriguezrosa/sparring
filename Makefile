# Project shortcuts. Usage: make <target>   (for example: make check)
.PHONY: install dev lint format typecheck test test-live check

install:  ## Install the exact dependencies from uv.lock
	uv sync

dev:  ## Start the development server with auto-reload
	uv run fastapi dev app/main.py

lint:  ## Look for errors and check formatting (changes nothing)
	uv run ruff check .
	uv run ruff format --check .

format:  ## Format the code and apply ruff's automatic fixes
	uv run ruff format .
	uv run ruff check --fix .

typecheck:  ## Type-check with mypy (strict mode)
	uv run mypy

test:  ## Run the tests (without the live ones)
	uv run pytest

test-live:  ## Run only the tests that call real APIs (needs .env, costs money)
	uv run pytest -m live -s

check: lint typecheck test  ## Everything that must pass before considering something done
