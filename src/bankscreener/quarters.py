"""Calendar-quarter helpers. Quarters are written '2024Q2'."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_Q_RE = re.compile(r"^(\d{4})Q([1-4])$", re.IGNORECASE)
_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


@dataclass(frozen=True, order=True)
class Quarter:
    year: int
    q: int

    @classmethod
    def parse(cls, text: str) -> "Quarter":
        m = _Q_RE.match(text.strip())
        if not m:
            raise ValueError(f"bad quarter {text!r}; expected e.g. 2024Q2")
        return cls(int(m.group(1)), int(m.group(2)))

    @classmethod
    def from_date(cls, d: date) -> "Quarter":
        if (d.month, d.day) not in _QUARTER_END.values():
            raise ValueError(f"{d} is not a quarter-end date")
        return cls(d.year, (d.month - 1) // 3 + 1)

    @classmethod
    def from_mmddyyyy(cls, text: str) -> "Quarter":
        return cls.from_date(date(int(text[4:8]), int(text[0:2]), int(text[2:4])))

    @property
    def end_date(self) -> date:
        m, d = _QUARTER_END[self.q]
        return date(self.year, m, d)

    @property
    def mmddyyyy(self) -> str:
        return self.end_date.strftime("%m%d%Y")

    def prev(self) -> "Quarter":
        return Quarter(self.year - 1, 4) if self.q == 1 else Quarter(self.year, self.q - 1)

    def next(self) -> "Quarter":
        return Quarter(self.year + 1, 1) if self.q == 4 else Quarter(self.year, self.q + 1)

    def __str__(self) -> str:
        return f"{self.year}Q{self.q}"


def quarter_range(start: Quarter, end: Quarter) -> list[Quarter]:
    out, q = [], start
    while q <= end:
        out.append(q)
        q = q.next()
    return out


def latest_possible(today: date | None = None) -> Quarter:
    """Most recent quarter whose Call Reports could be public.

    Call Reports are due 30 days after quarter end (35 for some filers) and
    appear in CDR bulk data shortly after, so a quarter is treated as
    possibly available 45 days after it ends. The download step still checks
    what the FFIEC actually offers.
    """
    today = today or date.today()
    q = Quarter.from_date(_last_quarter_end(today))
    while (today - q.end_date).days < 45:
        q = q.prev()
    return q


def _last_quarter_end(d: date) -> date:
    q = (d.month - 1) // 3
    if q == 0:
        return date(d.year - 1, 12, 31)
    m, day = _QUARTER_END[q]
    return date(d.year, m, day)
