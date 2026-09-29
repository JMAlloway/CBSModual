import pandas as pd

from bankscreener import db
from bankscreener.load import load_all, load_quarter
from bankscreener.parse_cdr import find_zips, read_zip
from bankscreener.quarters import Quarter


def test_read_zip_merges_split_schedules(cdr_zip):
    cq = read_zip(cdr_zip, {"RCFD2170", "RCON2170", "RIAD4340", "RIAD4074", "RIAD4079", "RIAD9999"})
    assert cq.quarter == Quarter(2024, 2)
    assert sorted(cq.items.index) == [111, 222, 333]
    assert cq.items.loc[111, "RIAD4079"] == "4"
    assert pd.isna(cq.items.loc[222, "RIAD4074"])
    assert cq.missing_columns == {"RIAD9999"}
    assert cq.por.loc[cq.por.idrssd == 222, "name"].item() == "COMMUNITY BANK"


def test_find_zips(cdr_zip):
    assert find_zips(cdr_zip.parent) == {Quarter(2024, 2): cdr_zip}


def _cfg_for(tmp_path, cfg, cdr_zip):
    cfg.paths["raw_cdr"] = cdr_zip.parent
    cfg.paths["db"] = tmp_path / "bank.duckdb"
    return cfg


def test_load_is_idempotent(tmp_path, cfg, cdr_zip):
    cfg = _cfg_for(tmp_path, cfg, cdr_zip)
    con = db.connect(cfg.path("db"))
    [r] = load_all(con, cfg, [Quarter(2024, 2)])
    assert r.status == "loaded" and r.banks == 4
    assert r.filing_types == {"031": 1, "051": 2, "041": 1}

    raw = con.execute("SELECT * FROM bank_quarter_raw ORDER BY idrssd").df().set_index("idrssd")
    assert raw.loc[111, "total_assets"] == 1000       # RCFD
    assert raw.loc[222, "total_assets"] == 500        # RCON
    assert raw.loc[111, "total_deposits"] == 700      # RCON + RCFN
    assert raw.loc[222, "total_deposits"] == 400
    assert pd.isna(raw.loc[444, "total_assets"])       # in POR, no schedule rows

    [again] = load_all(con, cfg, [Quarter(2024, 2)])
    assert again.status == "skipped"
    forced = load_quarter(con, cfg, cdr_zip, force=True)
    assert forced.status == "loaded"
    assert con.execute("SELECT count(*) FROM bank_quarter_raw").fetchone()[0] == 4

    banks = con.execute("SELECT * FROM banks WHERE idrssd = 222").df().iloc[0]
    assert banks["state"] == "IL" and banks["filing_type"] == "051"
    assert banks["first_quarter"] == banks["last_quarter"] == "2024Q2"
