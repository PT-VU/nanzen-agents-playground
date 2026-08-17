.PHONY: install style test run

install:
	uv sync

style:
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

test:
	uv run pytest -v

run:
	uv run python -m challenge.runner $(ARGS)
