from glob import glob

import pycodestyle
import pytest
from pylint import epylint as lint


class LintError(Exception):
    pass


class TestCodeLinting:
    @pytest.mark.skip(reason="test linting on a as-needed basis")
    def test_pylint(self):
        (stdout, _) = lint.py_run("liaa", return_std=True)
        errors = stdout.read()
        if errors.strip():
            raise LintError(errors)

    @pytest.mark.skip(reason="test linting on a as-needed basis")
    def test_pep8(self):
        style = pycodestyle.StyleGuide()
        files = glob("liaa/**/*.py", recursive=True)
        result = style.check_files(files)
        if result.total_errors > 0:
            raise LintError("Code style errors found.")
