import os
import re
import sys
from pathlib import Path

import pytest


# Keep package imports stable whether pytest is launched from the repository
# root or from course_extraction/ (the documented invocation location).
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def pytest_configure(config):
    # A test run inside an isolated Windows process can leave the system pytest
    # temp root owned by that process account, making later runs by the user
    # fail before tmp_path-backed tests start. Keep the default temp tree in the
    # repository and separate it by the effective Windows account so an
    # isolated run cannot lock the user's test directory.
    if config.option.basetemp is None:
        try:
            account = os.getlogin()
        except OSError:
            account = "default"
        account = re.sub(r"[^A-Za-z0-9_.-]+", "_", account).lower()
        config.option.basetemp = str(
            REPOSITORY_ROOT / f".pytest_tmp-{account}"
        )

    config.addinivalue_line(
        "markers",
        "live: slow test that requires network access to CUHK course catalog website",
    )


def pytest_addoption(parser):
    parser.addoption(
        "--course-options",
        action="store",
        default=None,
        metavar="LIST",
        help=(
            "limit live catalogue checks to subject option indexes; accepts "
            "individual values and inclusive ranges (for example: "
            "--course-options '1-50, 101-150')"
        ),
    )
