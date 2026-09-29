"""Read FFIEC CDR "Call Reports -- Single Period" bulk zips.

Each zip holds one tab-delimited file per schedule (large schedules are
split into "(1 of 2)" parts) plus a POR file with bank identity. In schedule
files row 1 is MDRM codes and row 2 is descriptions. Only the columns the
field spec asks for are read.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .quarters import Quarter

_DATE_RE = re.compile(r"(\d{8})")
ENCODING = "latin-1"

POR_COLUMNS = {
    "IDRSSD": "idrssd",
    "Financial Institution Name": "name",
    "Financial Institution City": "city",
    "Financial Institution State": "state",
    "Financial Institution Filing Type": "filing_type",
}


@dataclass
class CdrQuarter:
    quarter: Quarter
    por: pd.DataFrame  # idrssd, name, city, state, filing_type
    items: pd.DataFrame  # index idrssd, one column per MDRM code found
    missing_columns: set[str]  # wanted codes absent from every schedule file


def quarter_from_filename(name: str) -> Quarter | None:
    for token in _DATE_RE.findall(Path(name).name):
        try:
            return Quarter.from_mmddyyyy(token)
        except ValueError:
            continue
    return None


def find_zips(raw_dir: Path) -> dict[Quarter, Path]:
    """Map quarter -> zip for every recognisable bulk zip in raw_dir."""
    found: dict[Quarter, Path] = {}
    for p in sorted(Path(raw_dir).glob("*.zip")):
        q = quarter_from_filename(p.name)
        if q is None:
            continue
        if q in found:
            raise ValueError(f"two zips for {q}: {found[q].name} and {p.name}")
        found[q] = p
    return found


def _header(raw: bytes) -> list[str]:
    first = raw.split(b"\n", 1)[0].decode(ENCODING).rstrip("\r")
    return [h.strip().strip('"').strip() for h in first.split("\t")]


def _read_tsv(raw: bytes, usecols: list[str], drop_description_row: bool) -> pd.DataFrame:
    df = pd.read_csv(
        io.BytesIO(raw),
        sep="\t",
        dtype=str,
        encoding=ENCODING,
        usecols=lambda c: c.strip().strip('"').strip() in usecols,
        skiprows=[1] if drop_description_row else None,
        keep_default_na=False,
        na_values=[""],
    )
    df.columns = [c.strip().strip('"').strip() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].str.strip().replace("", pd.NA)
    return df


def read_por(raw: bytes) -> pd.DataFrame:
    header = _header(raw)
    missing = set(POR_COLUMNS) - set(header)
    if missing:
        raise ValueError(f"POR file lacks columns {sorted(missing)}")
    df = _read_tsv(raw, list(POR_COLUMNS), drop_description_row=False)
    # Tolerate a description row if a release ever adds one.
    df = df[df["IDRSSD"].str.fullmatch(r"\d+", na=False)]
    df = df.rename(columns=POR_COLUMNS)
    df["idrssd"] = df["idrssd"].astype("int64")
    return df.reset_index(drop=True)


def read_schedule(raw: bytes, wanted: set[str]) -> pd.DataFrame | None:
    """Return wanted columns indexed by idrssd, or None if the file has none."""
    header = _header(raw)
    if "IDRSSD" not in header:
        return None
    cols = [c for c in header if c in wanted]
    if not cols:
        return None
    df = _read_tsv(raw, ["IDRSSD", *cols], drop_description_row=True)
    df = df[df["IDRSSD"].str.fullmatch(r"\d+", na=False)]
    df = df.set_index(df.pop("IDRSSD").astype("int64").rename("idrssd"))
    if df.index.duplicated().any():
        raise ValueError("duplicate IDRSSD rows in schedule file")
    return df


def read_zip(path: Path, wanted: set[str]) -> CdrQuarter:
    quarter = quarter_from_filename(path.name)
    if quarter is None:
        raise ValueError(f"cannot tell the quarter from {path.name}")

    por = None
    items = pd.DataFrame(index=pd.Index([], dtype="int64", name="idrssd"))
    with zipfile.ZipFile(path) as zf:
        for member in zf.namelist():
            base = Path(member).name
            if not base.lower().endswith(".txt"):
                continue
            raw = zf.read(member)
            if re.search(r"\bPOR\b", base):
                por = read_por(raw)
                continue
            sched = read_schedule(raw, wanted)
            if sched is None:
                continue
            # A code can appear in more than one file; keep the first non-null.
            overlap = [c for c in sched.columns if c in items.columns]
            items = items.join(sched.drop(columns=overlap), how="outer")
            for c in overlap:
                items[c] = items[c].combine_first(sched[c])
    if por is None:
        raise ValueError(f"{path.name}: no POR file in zip")

    return CdrQuarter(
        quarter=quarter,
        por=por,
        items=items,
        missing_columns=wanted - set(items.columns),
    )
