.PHONY: help prepare-dev test lint run

# local setup
VIRTUALENV=/usr/local/bin/virtualenv
VENV_PYTHON3=./virtualenv/bin/python3.7
SYS_PYTHON3=/usr/local/bin/python3.7

.DEFAULT: help
help:
	@echo "prepare-dev"
	@echo "  prepare dev env (dev use only)"
	@echo "test"
	@echo "  run test suite"
	@echo "run"
	@echo "  run application (live)"
	@echo "doc"
	@echo "  build sphinx documentation"

prep-dev:
	make venv

clean:
	rm -rf ${WORKDIR}/virtualenv

venv: ${VIRTUALENV}
	${VIRTUALENV} -p ${SYS_PYTHON3} ./virtualenv
	${VENV_PYTHON3} -m pip install --upgrade -r .requirements.lock --trusted-host pypi.python.org

lint: ${VENV_PYTHON3}
	${VENV_PYTHON3} -m pylint

freeze: $(VENV_PYTHON3)
	pip freeze > .requirements.lock

local-test: ${VENV_PYTHON3}
	${VENV_PYTHON3} -m pytest tests/*

ci-test:
	python -m pytest tests/*

doc: $(VENV_PYTHON3)
	$(VENV_PYTHON3) && cd docs; make html
