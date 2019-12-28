.PHONY: clean doc freeze help lint prep-dev-fresh prep-dev-lock test

SHELL := /bin/bash
VIRTUALENV=/usr/local/bin/virtualenv
VENV_PYTHON3=./virtualenv/bin/python3.7
SYS_PYTHON3=/usr/local/bin/python3.7

.DEFAULT: help

clean:
	rm -rf ${WORKDIR}/virtualenv
	rm -f ${WORKDIR}/.requirements.lock
	@echo "clean step finished"

doc:
	python && cd docs; make html
	@echo "doc step finished"

freeze:
	python -m pip freeze > .requirements.lock
	@echo "freeze step finished"

help:
	@echo "clean"
	@echo "	Remove local virtualenv"
	@echo "doc"
	@echo "  build sphinx documentation"
	@echo "freeze"
	@echo "  Freeze pip requirements"
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

lint:
	python -m pylint kademlia/
	@echo "lint step finished"

prep-dev-fresh:
	${VIRTUALENV} -p ${SYS_PYTHON3} ./virtualenv
	${VENV_PYTHON3} -m pip install --upgrade -r dev-requirements.txt -r requirements.txt --trusted-host pypi.python.org
	@echo "prep-dev-fresh step finished"

prep-dev-lock:
	${VIRTUALENV} -p ${SYS_PYTHON3} ./virtualenv
	${VENV_PYTHON3} -m pip install --upgrade -r .requirements.lock --trusted-host pypi.python.org
	@echo "prep-dev-lock step finished"

test:
	python -m pytest tests/* --cov-report term --cov=./
	@echo "test step finished"
