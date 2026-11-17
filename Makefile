# Common tasks. Backend commands run in backend/ with the project's virtualenv active.

.PHONY: install demo dev-backend dev-frontend test lint up docker-demo

install:            ## install backend (editable, with dev tools and Claude support) and frontend dependencies
	cd backend && pip install -e ".[dev,llm]"
	cd frontend && npm install

demo:               ## build the demo database: synthetic portfolio, matches, warnings, review queue (no API calls)
	cd backend && python -m app.cli demo

dev-backend:        ## API on :8000 with auto-reload
	cd backend && uvicorn app.main:app --reload --port 8000

dev-frontend:       ## React dev server on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

test:               ## backend tests + frontend typecheck
	cd backend && python -m pytest
	cd frontend && npm run typecheck

lint:
	cd backend && ruff check app tests && ruff format --check app tests

up:                 ## full stack in Docker on http://localhost:8080 (then: make docker-demo)
	docker compose up --build

docker-demo:        ## build the demo database inside the running Docker stack
	docker compose exec backend python -m app.cli demo
