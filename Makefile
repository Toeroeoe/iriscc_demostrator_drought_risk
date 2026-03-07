VENV=.venv
PY=$(VENV)/bin/python
PIP=$(VENV)/bin/pip

.PHONY: install run clean

install:
	python -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

run:
	python -m shiny --reload app

clean:
	rm -rf $(VENV) __pycache__ .pytest_cache
