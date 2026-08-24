.PHONY: up down logs ingest test test-unit backend-shell backend frontend

up:
	docker compose up --build

# --- Local (non-Docker) dev servers -----------------------------------------
# Needs: `docker compose up -d db` running, backend/.venv and frontend/node_modules
# already installed, and backend/.env with your local settings (DATABASE_URL,
# OLLAMA_MODEL, ports, etc. — see backend/.env or .env.example for the fields).
backend:
	cd backend && ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 3400

frontend:
	cd frontend && npm run dev -- --port 3500

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
