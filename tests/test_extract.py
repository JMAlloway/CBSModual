import pandas as pd

from bankscreener.config import Field
from bankscreener.extract import coalesce, extract

ASSETS = Field("total_assets", "2170", "RC", "stock", ("RCFD", "RCON"))
DEPOSITS = Field("total_deposits", "2200", "RC", "stock", ("RCON",), ("RCFN",))


def frame(**cols):
    return pd.DataFrame(cols, index=pd.Index([1, 2, 3, 4], name="idrssd"))


def test_rcfd_wins_when_present_and_non_null():
    items = frame(RCFD2170=["1000", None, "0", None], RCON2170=["900", "500", "7", None])
    out = coalesce(items, ASSETS)
    assert out.tolist() == [1000, 500, 0, pd.NA]


def test_rcon_only_when_rcfd_column_absent():
    items = frame(RCON2170=["900", "500", None, "1"])
    assert coalesce(items, ASSETS).tolist() == [900, 500, pd.NA, 1]


def test_neither_column_present_gives_null():
    assert coalesce(frame(OTHER=["1"] * 4), ASSETS).isna().all()


def test_sum_prefix_added_only_where_base_exists():
    items = frame(RCON2200=["600", "400", None, "10"], RCFN2200=["100", None, "5", "bad"])
    assert coalesce(items, DEPOSITS).tolist() == [700, 400, pd.NA, 10]


def test_unresolved_field_skipped():
    todo = Field("tier1_capital", None, "RCR", "stock", ("RCOA",))
    out = extract(frame(RCON2170=["1"] * 4), [ASSETS, todo])
    assert list(out.columns) == ["total_assets"]
