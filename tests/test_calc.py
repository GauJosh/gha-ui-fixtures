import os

import pytest

from fixture_app.calc import add, divide

FAIL = os.environ.get("FIXTURE_OUTCOME") == "fail"


def test_add():
    assert add(2, 3) == 5


def test_divide():
    assert divide(9, 3) == 3


@pytest.mark.skipif(not FAIL, reason="only fails when FIXTURE_OUTCOME=fail")
def test_divide_by_zero_is_handled():
    # Deliberate, deterministic failure: divide() does not guard against zero.
    assert divide(1, 0) == 0
