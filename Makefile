.PHONY: clean freeze help install-lock lint prep-dev-fresh prep-dev-lock test

.DEFAULT: help

clean:
	rm -rfv build/
	rm -rfv dist/
	rm -rfv liaa.egg-info/
	find . -name '*.pyc' -exec rm --force {}

freeze:
	python -m pip freeze > .requirements.lock
	@echo "freeze done"

install-lock:
	python -m pip install --upgrade -r requirements/.requirements.lock --trusted-host pypi.python.org

install:
	python -m pip install --upgrade -r requirements/requirements.txt -r requirements/dev-requirements.txt -r requirements/test-requirements.txt

lint:
	python -m pylint liaa/

format:
	python -m black liaa/*.py && python -m black tests/*.py

typing:
	python -m mypy liaa/*.py -v --disallow-any-explicit --disallow-untyped-defs --no-implicit-optional

test:
	python -m pytest -s tests/* --cov-report term --cov=./ -vx
