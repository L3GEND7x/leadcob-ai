import sqlite3, subprocess, sys, tempfile
from pathlib import Path


def test_v01_database_is_upgraded_on_startup():
    db = Path(tempfile.mkdtemp()) / "v01.db"
    con = sqlite3.connect(db)
    con.executescript("""
      CREATE TABLE companies (id INTEGER PRIMARY KEY, name VARCHAR(220), cnpj VARCHAR(14), segment VARCHAR(120),
        city VARCHAR(100), state VARCHAR(2), website VARCHAR(500), institutional_email VARCHAR(255), created_at TIMESTAMP);
      CREATE TABLE opportunities (id INTEGER PRIMARY KEY, company_id INTEGER, kind VARCHAR(30), title VARCHAR(250),
        description TEXT, evidence TEXT, source_name VARCHAR(120), source_url VARCHAR(1000), collected_at TIMESTAMP,
        score INTEGER, score_reason TEXT, status VARCHAR(30), confidence FLOAT, is_verified BOOLEAN);
    """)
    con.close()
    code = "from app.db.database import ensure_schema; ensure_schema()"
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, "-c", code], cwd=root, check=True, env={"DATABASE_URL": f"sqlite:///{db}", "PATH": ""})
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(opportunities)")}
    assert {"source_key", "relevance", "commercial_signal", "deadline"} <= cols
    tables = {r[0] for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "capture_runs" in tables
