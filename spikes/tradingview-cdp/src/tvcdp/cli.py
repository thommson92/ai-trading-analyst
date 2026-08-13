"""Kommandozeilen-Einstieg: jeder Testschritt einzeln ausfuehrbar, sowie ein
``run-all``, das die gesamte Sequenz durchlaeuft (Nutzervorgabe).

Jeder Aufruf:
- schreibt eine strukturierte JSON-Logzeile pro Schritt (stdout),
- persistiert das (redigierte) Rohergebnis unter ``results/<run-id>/``,
- gibt das Ergebnis zusaetzlich als lesbares JSON auf stdout aus,
- liefert einen von PASSED abweichenden Exit-Code ungleich 0 zurueck, damit
  sich das Harness in Skripten (z. B. der Windows-Anleitung) auswerten laesst.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from pathlib import Path
from typing import Any

import click

from .cdp_client import CdpSession
from .config import CdpConfig, SpikeConfig
from .diagnostics import EnvironmentInfo
from .logging_setup import configure_logging, log_step_result
from .orchestration import discover_target, open_session
from .probe_config import ProbeConfig
from .redaction import redact
from .results_store import new_run_directory, write_step_result, write_summary
from .steps import (
    step_cdp_reachability,
    step_closed_candle,
    step_error_cases,
    step_indicators,
    step_layout,
    step_multi_symbol,
    step_session_check,
    step_target_discovery,
    step_timeframe,
    step_watchlist,
)
from .steps.base import StepResult, StepStatus, run_step

_EXIT_BY_STATUS = {
    StepStatus.PASSED: 0,
    StepStatus.NOT_APPLICABLE: 0,
    StepStatus.INCONCLUSIVE: 2,
    StepStatus.FAILED: 1,
}


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _combined_indicator_read_js(probes: ProbeConfig) -> str | None:
    """Baut aus den vier Indikator-Sonden (falls alle konfiguriert sind) einen
    einzigen Ausdruck fuer step_multi_symbol -- kein separates Sondenformat
    noetig, Wiederverwendung der bereits fuer Schritt E.15 ermittelten Werte."""
    indicators = (
        probes.indicator_rsi_js,
        probes.indicator_rsi_ma_js,
        probes.indicator_ema5_js,
        probes.indicator_ema20_js,
    )
    if any(indicator is None for indicator in indicators):
        return None
    rsi_js, rsi_ma_js, ema5_js, ema20_js = indicators
    return (
        f"({{rsi: ({rsi_js}), rsi_ma: ({rsi_ma_js}), "
        f"ema5: ({ema5_js}), ema20: ({ema20_js})}})"
    )


def _emit(run_dir: Path, result: StepResult) -> None:
    """Gibt das Ergebnis auf stdout aus und persistiert es -- beide Wege
    durch dieselbe Redaction, nicht nur der Dateipfad. Eine Sonde wertet
    JavaScript im Kontext der laufenden TradingView-Instanz aus; liefert
    eine unbedacht formulierte Sonde einmal mehr zurueck als beabsichtigt,
    darf das nicht ausgerechnet auf der Konsole landen, waehrend die
    Ergebnisdatei sauber bleibt."""
    logger = configure_logging()
    log_step_result(logger, result.step_id, result.status.value)
    write_step_result(run_dir, result)
    click.echo(
        json.dumps(
            redact(
                {
                    "step_id": result.step_id,
                    "title": result.title,
                    "status": result.status.value,
                    "duration_seconds": round(result.duration_seconds, 3),
                    "details": result.details,
                    "error": result.error,
                }
            ),
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )


@contextlib.asynccontextmanager
async def _connected_session(
    cdp_config: CdpConfig, spike_config: SpikeConfig
) -> AsyncIterator[CdpSession]:
    outcome = discover_target(cdp_config, spike_config.target_title_pattern)
    if outcome.connection_error is not None:
        raise click.ClickException(f"CDP nicht erreichbar: {outcome.connection_error}")
    if outcome.matched_target is None:
        raise click.ClickException(
            f"Kein Ziel passt zum Muster '{spike_config.target_title_pattern}'. "
            f"Verfuegbare Titel: {[t.title for t in outcome.targets]}"
        )
    session = await open_session(outcome.matched_target, cdp_config)
    try:
        yield session
    finally:
        await session.close()


def _run(coro: Coroutine[Any, Any, StepResult], run_dir: Path) -> StepResult:
    result: StepResult = asyncio.run(coro)
    _emit(run_dir, result)
    return result


def _exit_with(result: StepResult) -> None:
    raise SystemExit(_EXIT_BY_STATUS[result.status])


@click.group()
def main() -> None:
    """Gate-G2-Spike: TradingView-Desktop-Anbindung ueber CDP. Kein Produktivcode."""


@main.command("environment")
def cmd_environment() -> None:
    """Betriebssystem, Version, Python-Version erfassen -- immer ausfuehrbar."""
    spike_config = SpikeConfig.from_env()
    run_dir = new_run_directory(spike_config.results_dir)

    async def _step() -> StepResult:
        async def _func() -> dict[str, Any]:
            info = EnvironmentInfo.collect()
            return {
                "operating_system": info.operating_system,
                "os_version": info.os_version,
                "architecture": info.architecture,
                "python_version": info.python_version,
                "hostname": info.hostname,
                "collected_at": info.collected_at,
            }

        return await run_step("environment", "Umgebung erfasst", _func)

    result = _run(_step(), run_dir)
    _exit_with(result)


@main.command("reachability")
def cmd_reachability() -> None:
    """A.1/A.2: CDP-Debug-Port erreichbar?"""
    cdp_config = CdpConfig.from_env()
    spike_config = SpikeConfig.from_env()
    run_dir = new_run_directory(spike_config.results_dir)

    async def _step() -> StepResult:
        return await run_step(
            step_cdp_reachability.STEP_ID,
            step_cdp_reachability.TITLE,
            lambda: step_cdp_reachability.run(cdp_config),
        )

    result = _run(_step(), run_dir)
    _exit_with(result)


@main.command("target-discovery")
def cmd_target_discovery() -> None:
    """Welches CDP-Ziel ist TradingView Desktop?"""
    cdp_config = CdpConfig.from_env()
    spike_config = SpikeConfig.from_env()
    run_dir = new_run_directory(spike_config.results_dir)

    async def _step() -> StepResult:
        from .cdp_client import list_targets

        targets = list_targets(cdp_config)
        return await run_step(
            step_target_discovery.STEP_ID,
            step_target_discovery.TITLE,
            lambda: step_target_discovery.run(targets, spike_config.target_title_pattern),
        )

    result = _run(_step(), run_dir)
    _exit_with(result)


def _session_command(
    name: str,
    step_module: Any,
    build_coroutine: Callable[[CdpSession, ProbeConfig, SpikeConfig], Awaitable[StepResult]],
) -> Callable[[], None]:
    """Fabrik fuer die sich wiederholende Struktur "Session oeffnen, einen
    Schritt ausfuehren, Session schliessen" -- vermeidet sieben nahezu
    identische Klick-Kommandos."""

    def _command() -> None:
        cdp_config = CdpConfig.from_env()
        spike_config = SpikeConfig.from_env()
        probe_config = ProbeConfig.from_env()
        run_dir = new_run_directory(spike_config.results_dir)

        async def _step() -> StepResult:
            try:
                async with _connected_session(cdp_config, spike_config) as session:
                    return await build_coroutine(session, probe_config, spike_config)
            except click.ClickException:
                raise
            except Exception as exc:
                from datetime import UTC, datetime

                now = datetime.now(UTC)
                return StepResult(
                    step_id=step_module.STEP_ID,
                    title=step_module.TITLE,
                    status=StepStatus.FAILED,
                    started_at=now,
                    finished_at=now,
                    error=f"{type(exc).__name__}: {exc}",
                )

        result = _run(_step(), run_dir)
        _exit_with(result)

    _command.__name__ = name
    return _command


main.command("session-check")(
    _session_command(
        "session_check",
        step_session_check,
        lambda session, probes, _spike: run_step(
            step_session_check.STEP_ID,
            step_session_check.TITLE,
            lambda: step_session_check.run(session, probes.session_authenticated_js),
        ),
    )
)

main.command("watchlist")(
    _session_command(
        "watchlist",
        step_watchlist,
        lambda session, probes, _spike: run_step(
            step_watchlist.STEP_ID,
            step_watchlist.TITLE,
            lambda: step_watchlist.run(session, probes.watchlist_js),
        ),
    )
)

main.command("layout")(
    _session_command(
        "layout",
        step_layout,
        lambda session, probes, spike: run_step(
            step_layout.STEP_ID,
            step_layout.TITLE,
            lambda: step_layout.run(session, probes.layout_name_js, spike.expected_layout),
        ),
    )
)

main.command("timeframe")(
    _session_command(
        "timeframe",
        step_timeframe,
        lambda session, probes, _spike: run_step(
            step_timeframe.STEP_ID,
            step_timeframe.TITLE,
            lambda: step_timeframe.run(session, probes.timeframe_minutes_js),
        ),
    )
)

main.command("closed-candle")(
    _session_command(
        "closed_candle",
        step_closed_candle,
        lambda session, probes, _spike: run_step(
            step_closed_candle.STEP_ID,
            step_closed_candle.TITLE,
            lambda: step_closed_candle.run(session, probes.last_closed_candle_js),
        ),
    )
)

main.command("indicators")(
    _session_command(
        "indicators",
        step_indicators,
        lambda session, probes, _spike: run_step(
            step_indicators.STEP_ID,
            step_indicators.TITLE,
            lambda: step_indicators.run(
                session,
                probes.indicator_rsi_js,
                probes.indicator_rsi_ma_js,
                probes.indicator_ema5_js,
                probes.indicator_ema20_js,
            ),
        ),
    )
)

main.command("multi-symbol")(
    _session_command(
        "multi_symbol_run",
        step_multi_symbol,
        lambda session, probes, spike: run_step(
            step_multi_symbol.STEP_ID,
            step_multi_symbol.TITLE,
            lambda: step_multi_symbol.run(
                session,
                list(spike.watchlist_probe_names),
                probes.change_symbol_js_template,
                _combined_indicator_read_js(probes),
                spike.multi_symbol_switch_timeout_seconds,
            ),
        ),
    )
)


@main.command("error-cases")
def cmd_error_cases() -> None:
    """I.23: werden Fehlerfaelle erkannt statt zu Default-Werten zu fuehren?"""
    cdp_config = CdpConfig.from_env()
    spike_config = SpikeConfig.from_env()
    run_dir = new_run_directory(spike_config.results_dir)
    unreachable_config = CdpConfig(port=_unused_local_port(), connect_timeout_seconds=1.0)

    async def _step() -> StepResult:
        outcome = discover_target(cdp_config, spike_config.target_title_pattern)
        session: CdpSession | None = None
        if outcome.matched_target is not None:
            session = await open_session(outcome.matched_target, cdp_config)
        try:
            return await run_step(
                step_error_cases.STEP_ID,
                step_error_cases.TITLE,
                lambda: step_error_cases.run(session, unreachable_config),
            )
        finally:
            if session is not None:
                await session.close()

    result = _run(_step(), run_dir)
    _exit_with(result)


@main.command("run-all")
def cmd_run_all() -> None:
    """Fuehrt die gesamte Testsequenz aus und schreibt eine Zusammenfassung."""
    cdp_config = CdpConfig.from_env()
    spike_config = SpikeConfig.from_env()
    probe_config = ProbeConfig.from_env()
    run_dir = new_run_directory(spike_config.results_dir)
    results: list[StepResult] = []

    async def _collect() -> None:
        async def _env_step() -> StepResult:
            async def _func() -> dict[str, Any]:
                info = EnvironmentInfo.collect()
                return {
                    "operating_system": info.operating_system,
                    "os_version": info.os_version,
                    "architecture": info.architecture,
                    "python_version": info.python_version,
                    "hostname": info.hostname,
                    "collected_at": info.collected_at,
                }

            return await run_step("environment", "Umgebung erfasst", _func)

        results.append(await _env_step())
        results.append(
            await run_step(
                step_cdp_reachability.STEP_ID,
                step_cdp_reachability.TITLE,
                lambda: step_cdp_reachability.run(cdp_config),
            )
        )

        from .cdp_client import CdpConnectionError, list_targets

        try:
            targets = list_targets(cdp_config)
        except CdpConnectionError:
            targets = []

        results.append(
            await run_step(
                step_target_discovery.STEP_ID,
                step_target_discovery.TITLE,
                lambda: step_target_discovery.run(targets, spike_config.target_title_pattern),
            )
        )

        outcome = discover_target(cdp_config, spike_config.target_title_pattern)
        session: CdpSession | None = None
        if outcome.matched_target is not None:
            session = await open_session(outcome.matched_target, cdp_config)

        try:
            session_steps: list[tuple[str, str, Callable[[], Awaitable[dict[str, Any]]]]] = [
                (
                    step_session_check.STEP_ID,
                    step_session_check.TITLE,
                    lambda: step_session_check.run(
                        session, probe_config.session_authenticated_js  # type: ignore[arg-type]
                    ),
                ),
                (
                    step_watchlist.STEP_ID,
                    step_watchlist.TITLE,
                    lambda: step_watchlist.run(
                        session, probe_config.watchlist_js  # type: ignore[arg-type]
                    ),
                ),
                (
                    step_layout.STEP_ID,
                    step_layout.TITLE,
                    lambda: step_layout.run(
                        session,  # type: ignore[arg-type]
                        probe_config.layout_name_js,
                        spike_config.expected_layout,
                    ),
                ),
                (
                    step_timeframe.STEP_ID,
                    step_timeframe.TITLE,
                    lambda: step_timeframe.run(
                        session, probe_config.timeframe_minutes_js  # type: ignore[arg-type]
                    ),
                ),
                (
                    step_closed_candle.STEP_ID,
                    step_closed_candle.TITLE,
                    lambda: step_closed_candle.run(
                        session, probe_config.last_closed_candle_js  # type: ignore[arg-type]
                    ),
                ),
                (
                    step_indicators.STEP_ID,
                    step_indicators.TITLE,
                    lambda: step_indicators.run(
                        session,  # type: ignore[arg-type]
                        probe_config.indicator_rsi_js,
                        probe_config.indicator_rsi_ma_js,
                        probe_config.indicator_ema5_js,
                        probe_config.indicator_ema20_js,
                    ),
                ),
                (
                    step_multi_symbol.STEP_ID,
                    step_multi_symbol.TITLE,
                    lambda: step_multi_symbol.run(
                        session,  # type: ignore[arg-type]
                        list(spike_config.watchlist_probe_names),
                        probe_config.change_symbol_js_template,
                        _combined_indicator_read_js(probe_config),
                        spike_config.multi_symbol_switch_timeout_seconds,
                    ),
                ),
            ]
            for step_id, title, factory in session_steps:
                if session is None:
                    from datetime import UTC, datetime

                    now = datetime.now(UTC)
                    results.append(
                        StepResult(
                            step_id=step_id,
                            title=title,
                            status=StepStatus.NOT_APPLICABLE,
                            started_at=now,
                            finished_at=now,
                            details={"reason": "Kein TradingView-Ziel verbunden."},
                        )
                    )
                else:
                    results.append(await run_step(step_id, title, factory))

            unreachable_config = CdpConfig(port=_unused_local_port(), connect_timeout_seconds=1.0)
            results.append(
                await run_step(
                    step_error_cases.STEP_ID,
                    step_error_cases.TITLE,
                    lambda: step_error_cases.run(session, unreachable_config),
                )
            )
        finally:
            if session is not None:
                await session.close()

    asyncio.run(_collect())

    for result in results:
        _emit(run_dir, result)
    write_summary(run_dir, results)

    failed = [r for r in results if r.status is StepStatus.FAILED]
    click.echo(f"\n{len(results)} Schritte, {len(failed)} FAILED. Ergebnisse unter: {run_dir}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
