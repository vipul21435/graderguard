# Developer entry points. Every target runs through uv so the locked toolchain is used.
.PHONY: install lint format typecheck test cov check docker clean

IMAGE ?= graderguard:dev

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

# Build the image, smoke-test the CLI, then prune only this project's dangling images.
docker:
	docker build -t $(IMAGE) .
	docker run --rm $(IMAGE) --version
	docker image prune -f --filter label=project=graderguard

clean:
	rm -rf .mypy_cache .ruff_cache .pytest_cache .coverage coverage.xml htmlcov
