.PHONY: ci-test clean doc freeze help local-test lint prep-dev-fresh prep-dev-lock

VIRTUALENV=/usr/local/bin/virtualenv
VENV_PYTHON3=./virtualenv/bin/python3.7
SYS_PYTHON3=/usr/local/bin/python3.7

.DEFAULT: help

ci-test:
	python -m pytest tests/*
	@echo "ci-test step finished"

clean:
	rm -rf ${WORKDIR}/virtualenv
	rm -f ${WORKDIR}/.requirements.lock
	@echo "clean step finished"

doc: $(VENV_PYTHON3)
	$(VENV_PYTHON3) && cd docs; make html
	@echo "doc step finished"

freeze: $(VENV_PYTHON3)
	${VENV_PYTHON3} -m pip freeze > .requirements.lock
	@echo "freeze step finished"

help:
	@echo "ci-test"
	@echo "  run tests on travis CI"
	@echo "clean"
	@echo "	Remove local virtualenv"
	@echo "doc"
	@echo "  build sphinx documentation"
	@echo "freeze"
	@echo "  Freeze pip requirements"
	@echo "local-test"
	@echo "  run tests on local machine (uses static python)"
	@echo "lint"
	@echo "  Run linter"
	@echo "prep-dev-fresh"
	@echo "  prepare dev env from requirements.txt (dev use only)"
	@echo "prep-dev-lock"
	@echo "  prepare dev env from .requirements.lock (dev use only)"
	@echo "test"
	@echo "  run test suite"

local-test: ${VENV_PYTHON3}
	${VENV_PYTHON3} -m pytest tests/*
	@echo "local-test step finished"

lint: ${VENV_PYTHON3}
	${VENV_PYTHON3} -m pylint
	@echo "lint step finished"

prep-dev-fresh:
	${VIRTUALENV} -p ${SYS_PYTHON3} ./virtualenv
	${VENV_PYTHON3} -m pip install --upgrade -r dev-requirements.txt -r requirements.txt --trusted-host pypi.python.org
	@echo "prep-dev-fresh step finished"

prep-dev-lock:
	${VIRTUALENV} -p ${SYS_PYTHON3} ./virtualenv
	${VENV_PYTHON3} -m pip install --upgrade -r .requirements.lock --trusted-host pypi.python.org
	@echo "prep-dev-lock step finished"
