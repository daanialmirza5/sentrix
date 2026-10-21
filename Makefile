# Convenience targets (GNU make; on Windows use the PowerShell scripts listed in README).
PY := backend/.venv/Scripts/python.exe
ifeq ($(OS),)
PY := backend/.venv/bin/python
endif

.PHONY: install backend frontend seed test test-backend test-frontend e2e typecheck build audit verify-audit bench-drift reset-demo screenshots

install:        ; uv venv backend/.venv --python 3.12 && uv pip install --python $(PY) -r backend/requirements.txt && $(PY) scripts/download_model.py && cd frontend && npm install
backend:        ; cd backend && ../$(PY) -m uvicorn app.main:app --host 127.0.0.1 --port 8000
frontend:       ; cd frontend && npx vite --port 5173
seed:           ; $(PY) scripts/seed_demo.py
test: test-backend test-frontend
test-backend:   ; cd backend && ../$(PY) -m pytest
test-frontend:  ; cd frontend && npx tsc -b --noEmit && npx vitest run
e2e:            ; cd frontend && npx playwright test
typecheck:      ; cd frontend && npx tsc -b --noEmit
build:          ; cd frontend && npx vite build
audit:          ; backend/.venv/Scripts/pip-audit -r backend/requirements.txt; cd frontend && npm audit
verify-audit:   ; $(PY) scripts/verify_audit.py
bench-drift:    ; $(PY) scripts/eval_drift.py
reset-demo:     ; $(PY) scripts/reset_demo.py --yes
screenshots:    e2e
