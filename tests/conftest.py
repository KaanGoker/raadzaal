import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_db(tmp_path):
    from raadzaal import db
    con = db.connect(tmp_path / "t.db")
    yield con
    con.close()
