.DEFAULT_GOAL := run

PYTHON ?= python
VENV ?= .venv

.PHONY: setup run test demo groq-dev

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/Scripts/python -m pip install --upgrade pip
	$(VENV)/Scripts/python -m pip install -r requirements.lock
	docker build -t indigent-sandbox:1 sandbox/

run:
	$(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000

test:
	$(PYTHON) -m pytest -q

demo:
	INFERENCE_MODE=local $(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000

groq-dev:
	@$(PYTHON) -c "import os, sys; print('!!! WARNING: EXTERNAL INFERENCE ACTIVE (Groq dev mode) !!!'); sys.exit(0 if os.environ.get('GROQ_API_KEY') else 1)"
	INFERENCE_MODE=groq $(PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000
