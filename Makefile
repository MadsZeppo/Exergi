.PHONY: db-up migrate api worker web test demo

db-up:
	docker compose up -d postgres

migrate:
	uv run alembic upgrade head

api:
	uv run uvicorn commercial_twin.merchant_validation.api:app --reload --port 8000

worker:
	@echo "Database job worker is production-shaped but requires DATABASE_URL and PostgreSQL."

web:
	npm run dev

test:
	uv run pytest -q
	uv run ruff check .
	uv run mypy src

demo:
	uv run python scripts/run_end_to_end_demo.py
