import os
import sys
import tempfile

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Keep test logs/secret key out of the real project folders.
config.LOG_DIR = tempfile.mkdtemp()
config.JOBS_SYNC = True


@pytest.fixture(autouse=True)
def _test_defaults():
    """CSRF is off by default so the many route tests can POST plainly;
    tests/test_security.py turns it on explicitly to prove it works."""
    old_csrf = config.CSRF_ENABLED
    config.CSRF_ENABLED = False
    yield
    config.CSRF_ENABLED = old_csrf
