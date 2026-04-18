PYTHON ?= python

.PHONY: install run app test

install:
	$(PYTHON) -m pip install -e .[dev]

run:
	$(PYTHON) -m capacity_planner.pipeline

app:
	$(PYTHON) -m capacity_planner.app

test:
	pytest -q

