"""
Shared pytest fixtures for BrightDayBot tests.
"""

import pytest
from datetime import datetime, timezone


@pytest.fixture
def reference_date():
    """Fixed reference date for deterministic testing: March 15, 2025"""
    return datetime(2025, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def leap_year_reference():
    """Reference date in a leap year: February 28, 2024"""
    return datetime(2024, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
