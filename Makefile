.PHONY: up down logs ingest test test-unit backend-shell

up:
	docker compose up --build

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
