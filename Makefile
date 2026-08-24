.PHONY: up down logs ingest test test-unit backend-shell backend

up:
	docker compose up --build

# Native backend (recommended path — see README). Reads settings from
# backend/.env automatically; needs `docker compose up -d db` running first.
backend:
	cd backend && ./.venv/bin/uvicorn app.main:app --port 3400

down:
	docker compose down

logs:
	docker compose logs -f backend

ingest:
	docker compose exec backend python -m scripts.ingest

test:
	docker compose exec backend pytest

test-unit:
	docker compose exec backend pytest -k "not test_sessions_api"

backend-shell:
	docker compose exec backend sh
