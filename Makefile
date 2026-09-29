# Developer entry points. Every target runs through uv so the locked toolchain is used.
.PHONY: install lint format typecheck test cov check docker clean

install:
	uv sync --locked

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy

test:
	uv run pytest -q

cov:
	uv run pytest -q --cov --cov-report=term-missing --cov-report=xml

check: lint typecheck cov

clean:
	rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage coverage.xml htmlcov
