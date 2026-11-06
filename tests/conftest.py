import shutil
from pathlib import Path

import pytest

from salesops.config import Settings


@pytest.fixture
def settings(tmp_path):
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / "data", tmp_path / "data")
    return Settings(root=tmp_path, backend="offline")
