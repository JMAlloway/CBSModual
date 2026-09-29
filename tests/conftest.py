import zipfile
from pathlib import Path

import pytest

from bankscreener.config import load_config

ROOT = Path(__file__).resolve().parents[1]


def tsv(rows: list[list[str]]) -> bytes:
    return ("\r\n".join("\t".join(r) for r in rows) + "\r\n").encode("latin-1")


POR = tsv([
    ["IDRSSD", "FDIC Certificate Number", "Financial Institution Name", "Financial Institution City",
     "Financial Institution State", "Financial Institution Filing Type"],
    ["111", "1", "BIG BANK, N.A.", "NEW YORK", "NY", "31"],
    ["222", "2", "COMMUNITY BANK", "SPRINGFIELD", "IL", "51"],
    ["333", "3", "MID BANK", "AUSTIN", "TX", "41"],
    ["444", "4", "NO DATA BANK", "BOISE", "ID", "51"],
])

# RC: RCFD for the 031 filer, RCON for everyone; foreign deposits via RCFN.
RC = tsv([
    ['"IDRSSD"', "RCFD2170", "RCON2170", "RCON2200", "RCFN2200", "RCFD3210", "RCON3210", ""],
    ["", "TOTAL ASSETS", "TOTAL ASSETS", "DEPOSITS", "FOREIGN DEPOSITS", "EQUITY", "EQUITY", ""],
    ['"111"', "1000", "900", "600", "100", "80", "70", ""],
    ['"222"', "", "500", "400", "", "", "50", ""],
    ['"333"', "", "300", "250", "", "", "30", ""],
])
RI_1 = tsv([
    ["IDRSSD", "RIAD4340", "RIAD4074"],
    ["", "NET INCOME", "NII"],
    ["111", "10", "30"],
    ["222", "5", ""],
])
RI_2 = tsv([
    ["IDRSSD", "RIAD4079"],
    ["", "NONINT INCOME"],
    ["111", "4"],
    ["333", "2"],
])


@pytest.fixture
def cdr_zip(tmp_path) -> Path:
    path = tmp_path / "FFIEC CDR Call Bulk All Schedules 06302024.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("FFIEC CDR Call Bulk POR 06302024.txt", POR)
        zf.writestr("FFIEC CDR Call Schedule RC 06302024.txt", RC)
        zf.writestr("FFIEC CDR Call Schedule RI 06302024(1 of 2).txt", RI_1)
        zf.writestr("FFIEC CDR Call Schedule RI 06302024(2 of 2).txt", RI_2)
        zf.writestr("Readme.txt", b"ignore me")
    return path


@pytest.fixture
def cfg():
    return load_config(ROOT / "config.yaml")
