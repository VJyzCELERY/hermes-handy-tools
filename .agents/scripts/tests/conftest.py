"""Shared fixtures for agent-script tests."""

import shutil
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path():
    """Provide a disposable path inside the repository boundary."""
    root = Path(__file__).resolve().parents[3]
    path = root / "tmp" / f"pytest-{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path)
