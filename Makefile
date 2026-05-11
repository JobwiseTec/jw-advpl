.PHONY: help test test-fast bench lint format type validate ingest-real install-dev

help:
	@echo "plugadvpl — comandos dev"
	@echo "  test         — pytest unit + integration"
	@echo "  test-fast    — pytest unit only (-x)"
	@echo "  bench        — pytest-benchmark"
	@echo "  lint         — ruff check"
	@echo "  format       — ruff format"
	@echo "  type         — mypy --strict"
	@echo "  validate     — lint + type + test + bench"
	@echo "  ingest-real  — ingest em customizados-local (local only)"
	@echo "  install-dev  — uv sync"

install-dev:
	cd cli && uv sync

test:
	cd cli && uv run pytest tests/unit tests/integration -v

test-fast:
	cd cli && uv run pytest tests/unit -v -x

bench:
	cd cli && uv run pytest tests/bench --benchmark-only

lint:
	cd cli && uv run ruff check .
	python scripts/validate_plugin.py

format:
	cd cli && uv run ruff format .

type:
	cd cli && uv run mypy plugadvpl/

validate: lint type test bench

ingest-real:
	cd cli && uv run plugadvpl ingest customizados-local --workers 8
