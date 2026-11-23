.PHONY: install lint format typecheck test test-unit test-integration cov check run clean

install:
	uv sync --frozen
	uv run pre-commit install

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy

test-unit:
	uv run pytest tests/unit

test-integration:
	uv run pytest tests/integration -m integration

test:
	uv run pytest --cov --cov-report=term-missing

cov:
	uv run pytest --cov --cov-report=xml --cov-fail-under=85

check: lint typecheck test

run:
	uv run uvicorn app.main:app --reload --port 8000

clean:
	rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage coverage.xml htmlcov
