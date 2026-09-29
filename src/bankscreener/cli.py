"""`bank` command line."""
from __future__ import annotations

from pathlib import Path

import typer

from . import db
from .config import load_config
from .download import CdrSession, DownloadError, fetch_mdrm
from .parse_cdr import find_zips
from .quarters import Quarter, latest_possible, quarter_range

app = typer.Typer(add_completion=False, help="FFIEC Call Report / UBPR bank screener.")

ConfigOpt = typer.Option(Path("config.yaml"), "--config", "-c", help="Path to config.yaml")


def _range(cfg, start: str | None, end: str | None) -> tuple[Quarter, Quarter]:
    q_from = Quarter.parse(start or cfg.quarter_from)
    to = end or cfg.quarter_to
    q_to = latest_possible() if to.lower() == "latest" else Quarter.parse(to)
    return q_from, q_to


@app.command()
def download(
    start: str = typer.Option(None, "--from"),
    end: str = typer.Option(None, "--to"),
    force: bool = typer.Option(False, help="Re-download quarters already on disk"),
    config: Path = ConfigOpt,
):
    """Download CDR and UBPR bulk zips plus the MDRM dictionary."""
    cfg = load_config(config)
    q_from, q_to = _range(cfg, start, end)
    session = CdrSession()
    failures = 0

    for product, key in (("cdr", "raw_cdr"), ("ubpr", "raw_ubpr")):
        raw_dir = cfg.path(key)
        on_disk = find_zips(raw_dir) if raw_dir.exists() else {}
        try:
            offered = [q for q in session.available(product) if q_from <= q <= q_to]
        except (DownloadError, OSError) as e:
            typer.echo(f"[{product}] automated download unavailable: {e}")
            typer.echo(f"[{product}] drop zips into {raw_dir} manually; {len(on_disk)} already there.")
            failures += 1
            continue
        for q in offered:
            if q in on_disk and not force:
                typer.echo(f"[{product}] {q}: on disk, skipped")
                continue
            try:
                path = session.fetch(product, q, raw_dir)
                typer.echo(f"[{product}] {q}: saved {path.name}")
            except (DownloadError, OSError) as e:
                typer.echo(f"[{product}] {q}: FAILED ({e})")
                failures += 1

    mdrm_dir = cfg.path("raw_mdrm")
    if force or not (mdrm_dir / "MDRM.zip").exists():
        try:
            typer.echo(f"[mdrm] saved {fetch_mdrm(mdrm_dir).name}")
        except OSError as e:
            typer.echo(f"[mdrm] FAILED ({e}); place MDRM.zip in {mdrm_dir} manually")
            failures += 1
    if failures:
        typer.echo(f"{failures} download step(s) failed; the build uses whatever is on disk.")


@app.command()
def build(
    start: str = typer.Option(None, "--from"),
    end: str = typer.Option(None, "--to"),
    force: bool = typer.Option(False, help="Reload quarters already in the database"),
    config: Path = ConfigOpt,
):
    """Parse and extract Call Report data into DuckDB."""
    from .load import load_all

    cfg = load_config(config)
    q_from, q_to = _range(cfg, start, end)
    unresolved = [f.name for f in cfg.fields if not f.resolved]
    if unresolved:
        typer.echo(f"Fields with no code yet (skipped): {', '.join(unresolved)}")

    con = db.connect(cfg.path("db"))
    results = load_all(con, cfg, quarter_range(q_from, q_to), force)
    if not results:
        typer.echo(f"No CDR zips for {q_from}..{q_to} in {cfg.path('raw_cdr')}")
        raise typer.Exit(1)
    for r in results:
        if r.status == "skipped":
            typer.echo(f"{r.quarter}: already loaded, skipped")
            continue
        types = ", ".join(f"{k}={v}" for k, v in sorted(r.filing_types.items(), key=lambda kv: str(kv[0])))
        typer.echo(f"{r.quarter}: {r.banks} banks ({types})")
        if r.missing_columns:
            typer.echo(f"    columns not in any schedule file: {', '.join(r.missing_columns)}")


if __name__ == "__main__":
    app()
