.PHONY: clean freeze help install-lock lint prep-dev-fresh prep-dev-lock test

.DEFAULT: help

clean:
	rm -rf ./virtualenv
	rm -rfv ./build/
	rm -rfv ./dist/
	rm -rfv ./liaa.egg-info/
	@echo "clean step finished"

freeze:
	./virtualenv/bin/python3.7 -m pip freeze > .requirements.lock
	@echo "freeze step finished"

help:
	@echo "clean"
	@echo "	Remove local virtualenv"

	@echo "doc"
	@echo "  build sphinx documentation"

	@echo "freeze"
	@echo "  Freeze pip requirements"

	@echo "install-lock"
	@echo "  Install requirements via lockfile"

	@echo "lint"
	@echo "  Run linter"

	@echo "prep-dev-fresh"
	@echo "  prepare dev env from requirements.txt (dev use only)"

	@echo "prep-dev-lock"
	@echo "  prepare dev env from .requirements.lock (dev use only)"

	@echo "test-ci"
	@echo "  run tests on travis CI"

	@echo "test-local"
	@echo "  run tests on local machine (uses static python)"

install-lock:
	python -m pip install --upgrade -r .requirements.lock --trusted-host pypi.python.org
	@echo "install-lock step finished"

lint:
	python -m pylint liaa/
	@echo "lint step finished"

prep-dev-fresh:
	python3.7 -m venv ./virtualenv
	./virtualenv/bin/python -m pip install --upgrade -r dev-requirements.txt -r requirements.txt --trusted-host pypi.python.org
	@echo "prep-dev-fresh step finished"

prep-dev-lock:
	python3.7 -m venv ./virtualenv
	./virtualenv/bin/python -m pip install --upgrade -r .requirements.lock --trusted-host pypi.python.org
	@echo "prep-dev-lock step finished"

test:
	python -m pytest tests/* --cov-report term --cov=./
	@echo "test step finished"
