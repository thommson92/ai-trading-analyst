from __future__ import annotations

import json
import logging

import click

from .config import ConfigError, IbkrSpikeConfig
from .logging_setup import configure_logging
from .redaction import redact_mapping
from .results_store import save_result
from .steps import (
    step_connectivity,
    step_historical_bars,
    step_historical_coverage,
    step_multi_symbol,
    step_supplementary_data,
)

logger = logging.getLogger(__name__)


@click.group()
def main() -> None:
    configure_logging()


def _load_config() -> IbkrSpikeConfig:
    try:
        return IbkrSpikeConfig.from_env()
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc


def _emit(step_id: str, result: dict[str, object]) -> None:
    path = save_result(step_id, result)
    logger.info("Ergebnis gespeichert unter %s", path)
    click.echo(json.dumps(redact_mapping(result), indent=2, ensure_ascii=False))


@main.command()
def connectivity() -> None:
    """Schritt 1: Verbindung zu TWS/IB Gateway aufbauen und Basisinfos lesen."""
    config = _load_config()
    logger.info("Starte Schritt '%s'", step_connectivity.STEP_ID)
    result = step_connectivity.run(config)
    _emit(step_connectivity.STEP_ID, result)


@main.command(name="historical-bars")
@click.option(
    "--symbol", default="AAPL", show_default=True, help="US-Aktien-Symbol (SMART/USD)."
)
@click.option(
    "--duration",
    "duration_str",
    default="5 D",
    show_default=True,
    help="IBKR durationStr, z. B. '5 D'.",
)
@click.option(
    "--bar-size",
    default="15 mins",
    show_default=True,
    help="IBKR barSizeSetting, muss 195 Minuten ohne Rest teilen (z. B. '15 mins').",
)
@click.option(
    "--use-rth/--no-use-rth",
    default=True,
    show_default=True,
    help="Nur reguläre Handelszeit (RTH) anfordern -- Pre-/After-Market ausschließen.",
)
def historical_bars(symbol: str, duration_str: str, bar_size: str, use_rth: bool) -> None:
    """Schritt 3: Historische Bars laden und zu 195-Minuten-Kerzen aggregieren."""
    config = _load_config()
    logger.info("Starte Schritt '%s' fuer Symbol %s", step_historical_bars.STEP_ID, symbol)
    result = step_historical_bars.run(config, symbol, duration_str, bar_size, use_rth)
    _emit(step_historical_bars.STEP_ID, result)


@main.command(name="historical-coverage")
@click.option(
    "--symbol", default="AAPL", show_default=True, help="US-Aktien-Symbol (SMART/USD)."
)
@click.option(
    "--bar-size",
    default="15 mins",
    show_default=True,
    help="IBKR barSizeSetting, muss 195 Minuten ohne Rest teilen (z. B. '15 mins').",
)
@click.option(
    "--durations",
    default=",".join(step_historical_coverage.DEFAULT_DURATIONS),
    show_default=True,
    help="Kommagetrennte Liste von IBKR durationStr-Werten, aufsteigend getestet.",
)
@click.option(
    "--pacing-delay",
    "pacing_delay_seconds",
    default=step_historical_coverage.DEFAULT_PACING_DELAY_SECONDS,
    show_default=True,
    help="Pause in Sekunden zwischen den einzelnen Anfragen (Pacing-Schutz).",
)
def historical_coverage(
    symbol: str, bar_size: str, durations: str, pacing_delay_seconds: float
) -> None:
    """Schritt 4: Historische Abdeckung und Pacing-Verhalten pruefen."""
    config = _load_config()
    duration_list = [d.strip() for d in durations.split(",") if d.strip()]
    logger.info("Starte Schritt '%s' fuer Symbol %s", step_historical_coverage.STEP_ID, symbol)
    result = step_historical_coverage.run(
        config, symbol, bar_size, durations=duration_list, pacing_delay_seconds=pacing_delay_seconds
    )
    _emit(step_historical_coverage.STEP_ID, result)


@main.command(name="supplementary-data")
@click.option(
    "--symbol", default="AAPL", show_default=True, help="US-Aktien-Symbol (SMART/USD)."
)
def supplementary_data(symbol: str) -> None:
    """Schritt 6 (Frage 6): Earnings-Kalender, Analystenschaetzungen und
    Optionsketten mit Greeks pruefen (F9)."""
    config = _load_config()
    logger.info("Starte Schritt '%s' fuer Symbol %s", step_supplementary_data.STEP_ID, symbol)
    result = step_supplementary_data.run(config, symbol)
    _emit(step_supplementary_data.STEP_ID, result)


@main.command(name="multi-symbol")
@click.option(
    "--symbols",
    default=",".join(step_multi_symbol.DEFAULT_SYMBOLS),
    show_default=True,
    help="Kommagetrennte Liste von US-Aktien-Symbolen.",
)
@click.option(
    "--duration",
    "duration_str",
    default="5 D",
    show_default=True,
    help="IBKR durationStr, z. B. '5 D'.",
)
@click.option(
    "--bar-size",
    default="15 mins",
    show_default=True,
    help="IBKR barSizeSetting, muss 195 Minuten ohne Rest teilen (z. B. '15 mins').",
)
@click.option(
    "--use-rth/--no-use-rth",
    default=True,
    show_default=True,
    help="Nur reguläre Handelszeit (RTH) anfordern -- Pre-/After-Market ausschließen.",
)
def multi_symbol(symbols: str, duration_str: str, bar_size: str, use_rth: bool) -> None:
    """Schritt 7 (Frage 7): Mehrere Symbole ueber eine TWS-Verbindung
    durchlaufen und Laufzeit/Fehlerrate messen."""
    config = _load_config()
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    logger.info(
        "Starte Schritt '%s' fuer %d Symbole", step_multi_symbol.STEP_ID, len(symbol_list)
    )
    result = step_multi_symbol.run(config, symbol_list, duration_str, bar_size, use_rth)
    _emit(step_multi_symbol.STEP_ID, result)
