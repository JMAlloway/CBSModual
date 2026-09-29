"""Parse + extract: CDR zips -> bank_quarter_por and bank_quarter_raw."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import db
from .config import Config
from .extract import extract
from .parse_cdr import find_zips, read_zip
from .quarters import Quarter

SOURCE = "cdr"


@dataclass
class LoadResult:
    quarter: Quarter
    status: str  # loaded | skipped
    banks: int = 0
    missing_columns: tuple[str, ...] = ()
    filing_types: dict[str, int] | None = None


def normalize_filing_type(s: pd.Series) -> pd.Series:
    s = s.astype("string").str.strip()
    return s.where(~s.str.fullmatch(r"\d{1,3}", na=False), s.str.zfill(3))


def load_quarter(con, cfg: Config, path: Path, force: bool = False) -> LoadResult:
    from .parse_cdr import quarter_from_filename

    quarter = quarter_from_filename(path.name)
    sha = db.file_sha256(path)
    if not force and db.loaded_hash(con, SOURCE, str(quarter)) == sha:
        return LoadResult(quarter, "skipped")

    cq = read_zip(path, cfg.wanted_columns())
    por = cq.por.copy()
    por["filing_type"] = normalize_filing_type(por["filing_type"])
    por["quarter"] = str(quarter)
    por["report_date"] = quarter.end_date

    values = extract(cq.items, cfg.resolved_fields)
    # Every POR bank gets a row, even if it has no values in any schedule.
    raw = por[["idrssd", "quarter", "report_date", "filing_type"]].join(values, on="idrssd")

    con.execute("BEGIN")
    try:
        db.replace_quarter(con, "bank_quarter_por", str(quarter), por[["idrssd", "quarter", "report_date", "name", "city", "state", "filing_type"]])
        db.replace_quarter(con, "bank_quarter_raw", str(quarter), raw)
        db.record_load(con, SOURCE, str(quarter), path.name, sha)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    return LoadResult(
        quarter,
        "loaded",
        banks=len(raw),
        missing_columns=tuple(sorted(cq.missing_columns)),
        filing_types=raw["filing_type"].value_counts().to_dict(),
    )


def load_all(con, cfg: Config, quarters: list[Quarter], force: bool = False) -> list[LoadResult]:
    db.ensure_schema(con, cfg.fields)
    zips = find_zips(cfg.path("raw_cdr"))
    results = [load_quarter(con, cfg, zips[q], force) for q in quarters if q in zips]
    db.rebuild_banks(con)
    return results
