"""DuckDB storage: schema, idempotent per-quarter loads."""
from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb
import pandas as pd

from .config import Field

_SQL_TYPE = {"flag": "VARCHAR"}


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def ensure_schema(con: duckdb.DuckDBPyConnection, fields: list[Field]) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS load_log (
            source VARCHAR, quarter VARCHAR, file_name VARCHAR, sha256 VARCHAR,
            loaded_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (source, quarter))
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS bank_quarter_por (
            idrssd BIGINT, quarter VARCHAR, report_date DATE, name VARCHAR,
            city VARCHAR, state VARCHAR, filing_type VARCHAR,
            PRIMARY KEY (idrssd, quarter))
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS bank_quarter_raw (
            idrssd BIGINT, quarter VARCHAR, report_date DATE, filing_type VARCHAR,
            PRIMARY KEY (idrssd, quarter))
        """
    )
    existing = {r[0] for r in con.execute("SELECT column_name FROM (DESCRIBE bank_quarter_raw)").fetchall()}
    for f in fields:
        if f.resolved and f.name not in existing:
            con.execute(f'ALTER TABLE bank_quarter_raw ADD COLUMN "{f.name}" {_SQL_TYPE.get(f.kind, "DOUBLE")}')


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def loaded_hash(con: duckdb.DuckDBPyConnection, source: str, quarter: str) -> str | None:
    row = con.execute(
        "SELECT sha256 FROM load_log WHERE source = ? AND quarter = ?", [source, quarter]
    ).fetchone()
    return row[0] if row else None


def replace_quarter(
    con: duckdb.DuckDBPyConnection,
    table: str,
    quarter: str,
    df: pd.DataFrame,
) -> None:
    """Delete then insert one quarter's rows, matching columns by name."""
    con.execute(f"DELETE FROM {table} WHERE quarter = ?", [quarter])
    con.register("_incoming", df)
    cols = ", ".join(f'"{c}"' for c in df.columns)
    con.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _incoming")
    con.unregister("_incoming")


def record_load(con, source: str, quarter: str, file_name: str, sha256: str) -> None:
    con.execute("DELETE FROM load_log WHERE source = ? AND quarter = ?", [source, quarter])
    con.execute(
        "INSERT INTO load_log (source, quarter, file_name, sha256) VALUES (?, ?, ?, ?)",
        [source, quarter, file_name, sha256],
    )


def rebuild_banks(con: duckdb.DuckDBPyConnection) -> None:
    """banks: identity from each bank's most recent POR row."""
    con.execute(
        """
        CREATE OR REPLACE TABLE banks AS
        SELECT idrssd,
               arg_max(name, quarter)        AS name,
               arg_max(city, quarter)        AS city,
               arg_max(state, quarter)       AS state,
               arg_max(filing_type, quarter) AS filing_type,
               min(quarter)                  AS first_quarter,
               max(quarter)                  AS last_quarter
        FROM bank_quarter_por
        GROUP BY idrssd
        """
    )
