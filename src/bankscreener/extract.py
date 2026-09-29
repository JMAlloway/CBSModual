"""Turn raw MDRM columns into one column per configured field."""
from __future__ import annotations

import pandas as pd

from .config import Field


def coalesce(items: pd.DataFrame, field: Field) -> pd.Series:
    """First non-null value across field.prefixes, plus any sum_prefixes.

    RCFD beats RCON when both exist and RCFD is non-null (031 filers report
    consolidated RCFD; 041/051 filers report RCON). sum_prefixes (foreign
    offices, RCFN) are added only where the base value exists.
    """
    out = pd.Series(pd.NA, index=items.index, dtype="Float64")
    for prefix in field.prefixes:
        col = prefix + field.item
        if col in items.columns:
            out = out.fillna(_numeric(items[col]))
    for prefix in field.sum_prefixes:
        col = prefix + field.item
        if col in items.columns:
            out = out + _numeric(items[col]).fillna(0)
    return out.rename(field.name)


def coalesce_flag(items: pd.DataFrame, field: Field) -> pd.Series:
    out = pd.Series(pd.NA, index=items.index, dtype="string")
    for prefix in field.prefixes:
        col = prefix + field.item
        if col in items.columns:
            out = out.fillna(items[col].astype("string"))
    return out.rename(field.name)


def _numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("Float64")


def extract(items: pd.DataFrame, fields: list[Field]) -> pd.DataFrame:
    cols = {}
    for f in fields:
        if not f.resolved:
            continue
        cols[f.name] = coalesce_flag(items, f) if f.kind == "flag" else coalesce(items, f)
    return pd.DataFrame(cols, index=items.index)
