from __future__ import annotations

import re
from typing import Tuple

import pytest

from app.repository.employer_repository.job_repo import _parse_single_or_range


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("100000", (100000, 100000)),
        ("100000-150000", (100000, 150000)),
        ("  50000 ", (50000, 50000)),
        ("  2 - 5 ", (2, 5)),
        ("0", (0, 0)),
        (None, (None, None)),
        ("", (None, None)),
        ("abc", (None, None)),
        ("100-xyz", (None, None)),
        ("150000-100000", (None, None)),
        ("12-", (None, None)),
        ("-12", (None, None)),
    ],
)
def test_parse_single_or_range(raw, expected):
    assert _parse_single_or_range(raw) == expected
