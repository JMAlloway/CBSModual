# Bank screener — Call Report data pipeline

Pulls FFIEC Call Report (CDR) and UBPR bulk data, extracts a configured set
of MDRM fields, and builds valuation-screen metrics in DuckDB.

```
pip install -e ".[dev]"
bank download --from 2019Q4 --to latest   # or drop zips into data/raw/cdr, data/raw/ubpr
bank build                                # parse + extract (derive/validate: coming)
pytest
```

Configuration lives in `config.yaml` (quarter range, paths, scope, field spec).
Every filer is loaded; exports are limited to `scope.filing_types` (default 051).

Status: stage 1 (download, parse, extract). MDRM codes are unverified until
the dictionary check runs.
