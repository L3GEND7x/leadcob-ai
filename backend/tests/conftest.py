import os, sys, tempfile
from pathlib import Path

_DB = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
