"""Load config.yaml into typed objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

KINDS = {"stock", "ytd", "ratio", "flag"}
_DEFAULT_PREFIX_KEY = {"RI": "income_prefixes", "RIB": "income_prefixes", "RCR": "capital_prefixes"}


@dataclass(frozen=True)
class Field:
    name: str
    item: str | None
    schedule: str
    kind: str
    prefixes: tuple[str, ...]
    sum_prefixes: tuple[str, ...] = ()
    verify: bool = False

    @property
    def resolved(self) -> bool:
        return self.item is not None

    def columns(self) -> list[str]:
        """Every MDRM column (prefix + item) this field may read."""
        if not self.resolved:
            return []
        return [p + self.item for p in (*self.prefixes, *self.sum_prefixes)]


@dataclass
class Config:
    root: Path
    quarter_from: str
    quarter_to: str
    paths: dict[str, Path]
    filing_types: list[str]
    tax_rate: float
    beta_start: str
    beta_end: str
    fields: list[Field] = field(default_factory=list)

    def path(self, key: str) -> Path:
        return self.paths[key]

    @property
    def resolved_fields(self) -> list[Field]:
        return [f for f in self.fields if f.resolved]

    def wanted_columns(self) -> set[str]:
        return {c for f in self.fields for c in f.columns()}


def load_config(path: str | Path = "config.yaml") -> Config:
    path = Path(path).resolve()
    raw = yaml.safe_load(path.read_text())
    root = path.parent
    defaults = raw.get("defaults", {})

    fields = []
    for spec in raw["fields"]:
        item = spec.get("item")
        kind = spec["kind"]
        if kind not in KINDS:
            raise ValueError(f"field {spec['name']}: unknown kind {kind!r}")
        prefix_key = _DEFAULT_PREFIX_KEY.get(spec["schedule"], "balance_prefixes")
        fields.append(
            Field(
                name=spec["name"],
                item=None if item is None else str(item).upper(),
                schedule=spec["schedule"],
                kind=kind,
                prefixes=tuple(spec.get("prefixes") or defaults[prefix_key]),
                sum_prefixes=tuple(spec.get("sum_prefixes") or ()),
                verify=bool(spec.get("verify", False)),
            )
        )
    names = [f.name for f in fields]
    if len(names) != len(set(names)):
        raise ValueError("duplicate field names in config")

    return Config(
        root=root,
        quarter_from=str(raw["quarters"]["from"]),
        quarter_to=str(raw["quarters"]["to"]),
        paths={k: root / v for k, v in raw["paths"].items()},
        filing_types=[str(t) for t in raw["scope"]["filing_types"]],
        tax_rate=float(raw["assumptions"]["tax_rate"]),
        beta_start=str(raw["deposit_beta"]["start"]),
        beta_end=str(raw["deposit_beta"]["end"]),
        fields=fields,
    )
