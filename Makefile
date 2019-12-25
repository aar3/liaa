.PHONY: ci-test clean doc freeze help local-test lint prep-dev venv

VIRTUALENV=/usr/local/bin/virtualenv
VENV_PYTHON3=./virtualenv/bin/python3.7
SYS_PYTHON3=/usr/local/bin/python3.7

.DEFAULT: help

ci-test:
	python -m pytest tests/*

clean:
	rm -rf ${WORKDIR}/virtualenv

doc: $(VENV_PYTHON3)
	$(VENV_PYTHON3) && cd docs; make html

freeze: $(VENV_PYTHON3)
	pip freeze > .requirements.lock

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
	@echo "prep-dev"
	@echo "  prepare dev env (dev use only)"
	@echo "test"
	@echo "  run test suite"
	@echo "venv"
	@echo "  create local virtualenv"

local-test: ${VENV_PYTHON3}
	${VENV_PYTHON3} -m pytest tests/*

lint: ${VENV_PYTHON3}
	${VENV_PYTHON3} -m pylint

prep-dev:
	make venv

venv: ${VIRTUALENV}
	${VIRTUALENV} -p ${SYS_PYTHON3} ./virtualenv
	${VENV_PYTHON3} -m pip install --upgrade -r .requirements.lock --trusted-host pypi.python.org
