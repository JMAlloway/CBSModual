"""Fetch bulk zips from the FFIEC CDR public download page and the MDRM
dictionary from the Federal Reserve.

The CDR page is an ASP.NET WebForm: choosing a product posts the form back
to refresh the list of dates, and the download is another post-back. The
form is driven generically (by option text, not hard-coded control ids) so
small page changes don't break it. If anything fails the caller falls back
to whatever zips are already in data/raw/.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

import requests

from .quarters import Quarter

CDR_URL = "https://cdr.ffiec.gov/public/PWS/DownloadBulkData.aspx"
MDRM_URL = "https://www.federalreserve.gov/apps/mdrm/pdf/MDRM.zip"

PRODUCTS = {
    "cdr": "Call Reports -- Single Period",
    "ubpr": "UBPR Ratio -- Single Period",
}
USER_AGENT = "Mozilla/5.0 (personal bank-screener; public bulk data)"
TIMEOUT = 300


class DownloadError(RuntimeError):
    pass


@dataclass
class _Select:
    name: str
    options: list[tuple[str, str]] = field(default_factory=list)  # (value, text)
    selected: str | None = None


class _FormParser(HTMLParser):
    """Collects inputs and selects from the page's single ASP.NET form."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.action: str | None = None
        self.inputs: list[dict[str, str]] = []
        self.selects: list[_Select] = []
        self._select: _Select | None = None
        self._option: dict[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "form" and self.action is None:
            self.action = a.get("action")
        elif tag == "input":
            self.inputs.append(a)
        elif tag == "select":
            self._select = _Select(a.get("name", ""))
        elif tag == "option" and self._select is not None:
            self._option, self._text = a, []

    def handle_data(self, data):
        if self._option is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "option" and self._select is not None and self._option is not None:
            value = self._option.get("value", "")
            self._select.options.append((value, "".join(self._text).strip()))
            if "selected" in self._option:
                self._select.selected = value
            self._option = None
        elif tag == "select" and self._select is not None:
            self.selects.append(self._select)
            self._select = None


def _parse(html: str) -> _FormParser:
    p = _FormParser()
    p.feed(html)
    if not p.inputs:
        raise DownloadError("CDR page returned no form inputs (blocked or layout changed)")
    return p


def _base_fields(form: _FormParser) -> dict[str, str]:
    """Hidden fields plus the current state of every select."""
    data = {i["name"]: i.get("value", "") for i in form.inputs if i.get("type") == "hidden" and i.get("name")}
    for s in form.selects:
        if s.selected is not None:
            data[s.name] = s.selected
    return data


def _product_select(form: _FormParser, product_text: str) -> tuple[str, str]:
    for s in form.selects:
        for value, text in s.options:
            if text.strip().lower() == product_text.lower():
                return s.name, value
    raise DownloadError(f"product {product_text!r} not offered on the CDR page")


_DATE_TEXT = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _date_select(form: _FormParser) -> tuple[str, dict[Quarter, str]]:
    for s in form.selects:
        dates = {}
        for value, text in s.options:
            if _DATE_TEXT.match(text):
                d = datetime.strptime(text, "%m/%d/%Y").date()
                try:
                    dates[Quarter.from_date(d)] = value
                except ValueError:
                    continue
        if dates:
            return s.name, dates
    raise DownloadError("no reporting-period list found on the CDR page")


def _tab_delimited_radio(form: _FormParser) -> tuple[str, str] | None:
    for i in form.inputs:
        if i.get("type") == "radio" and re.search(r"tsv|tab", i.get("value", "") + i.get("id", ""), re.I):
            return i["name"], i["value"]
    return None


def _download_button(form: _FormParser) -> tuple[str, str]:
    for i in form.inputs:
        if i.get("type") == "submit" and i.get("value", "").strip().lower() == "download":
            return i["name"], i["value"]
    raise DownloadError("no Download button found on the CDR page")


class CdrSession:
    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self._forms: dict[str, _FormParser] = {}

    def _select_product(self, product: str) -> _FormParser:
        if product in self._forms:
            return self._forms[product]
        r = self.s.get(CDR_URL, timeout=60)
        r.raise_for_status()
        form = _parse(r.text)
        name, value = _product_select(form, PRODUCTS[product])
        data = _base_fields(form) | {name: value, "__EVENTTARGET": name, "__EVENTARGUMENT": ""}
        r = self.s.post(CDR_URL, data=data, timeout=60)
        r.raise_for_status()
        form = _parse(r.text)
        self._forms[product] = form
        return form

    def available(self, product: str) -> list[Quarter]:
        _, dates = _date_select(self._select_product(product))
        return sorted(dates)

    def fetch(self, product: str, quarter: Quarter, dest_dir: Path) -> Path:
        form = self._select_product(product)
        pname, pvalue = _product_select(form, PRODUCTS[product])
        dname, dates = _date_select(form)
        if quarter not in dates:
            raise DownloadError(f"{quarter} not offered for {PRODUCTS[product]}")
        data = _base_fields(form) | {pname: pvalue, dname: dates[quarter], "__EVENTTARGET": "", "__EVENTARGUMENT": ""}
        if radio := _tab_delimited_radio(form):
            data[radio[0]] = radio[1]
        bname, bvalue = _download_button(form)
        data[bname] = bvalue

        r = self.s.post(CDR_URL, data=data, timeout=TIMEOUT, stream=True)
        r.raise_for_status()
        if "zip" not in r.headers.get("Content-Type", "") and "attachment" not in r.headers.get("Content-Disposition", ""):
            raise DownloadError(f"{product} {quarter}: server did not return a file")
        name = _filename(r.headers.get("Content-Disposition", "")) or f"{product}_{quarter.mmddyyyy}.zip"
        if quarter.mmddyyyy not in name:
            name = f"{Path(name).stem} {quarter.mmddyyyy}.zip"
        return _save(r, dest_dir / name)


def _filename(disposition: str) -> str | None:
    m = re.search(r'filename="?([^";]+)"?', disposition)
    return m.group(1).strip() if m else None


def _save(r: requests.Response, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with open(tmp, "wb") as fh:
        for chunk in r.iter_content(1 << 20):
            fh.write(chunk)
    tmp.replace(dest)
    return dest


def fetch_mdrm(dest_dir: Path) -> Path:
    r = requests.get(MDRM_URL, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, stream=True)
    r.raise_for_status()
    return _save(r, dest_dir / "MDRM.zip")
