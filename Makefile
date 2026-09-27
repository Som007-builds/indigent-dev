.DEFAULT_GOAL := run

PYTHON ?= python3
VENV ?= .venv

# Cross-platform virtual environment paths
ifeq ($(OS),Windows_NT)
    VENV_PYTHON = $(VENV)/Scripts/python
    VENV_PIP = $(VENV)/Scripts/pip
else
    VENV_PYTHON = $(VENV)/bin/python
    VENV_PIP = $(VENV)/bin/pip
endif

.PHONY: setup run test demo groq-dev

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.lock
	docker build -t indigent-sandbox:1 sandbox/

run:
	$(VENV_PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000

test:
	$(VENV_PYTHON) -m pytest -q

demo:
	INFERENCE_MODE=local $(VENV_PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000

groq-dev:
	@$(PYTHON) -c "import os, sys; print('!!! WARNING: EXTERNAL INFERENCE ACTIVE (Groq dev mode) !!!'); sys.exit(0 if os.environ.get('GROQ_API_KEY') else 1)"
	INFERENCE_MODE=groq $(VENV_PYTHON) -m uvicorn app.main:app --host 127.0.0.1 --port 8000
