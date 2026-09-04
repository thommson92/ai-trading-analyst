"""Tests des Validierungscharts.

Geprueft wird der Inhalt der Nutzlast, nicht das Aussehen: Ob eine Kerze als
Kandidat, als verworfen oder als Folgetrigger einer Episode markiert ist,
entscheidet ueber das, was der Betrachter glaubt zu sehen.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai_trading_analyst.domain.screening import (
    CandidateRuleParameters,
    Candle,
    CandleSeries,
    IndicatorValues,
)
from ai_trading_analyst.presentation.validation_chart import (
    build_chart_payload,
    render_chart_html,
)

_EPOCH = datetime(2024, 1, 2, tzinfo=UTC)
_TIMEFRAME = timedelta(minutes=195)
_BASELINE_EMA = 99.0

PARAMS = CandidateRuleParameters(
    required_crossing_signals=2, signal_lookback_previous_candles=5, warmup_candles=10
)
SERIES_LENGTH = 30


def _serie(overrides: dict[int, IndicatorValues] | None = None) -> CandleSeries:
    """Wie in den Screening-Tests: ruhige Baseline ueber dem EMA20."""
    overrides = overrides or {}
    candles = tuple(
        Candle(
            timestamp=_EPOCH + i * _TIMEFRAME,
            daily_candle_index=1 if i % 2 == 0 else 2,
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
            volume=1_000.0,
        )
        for i in range(SERIES_LENGTH)
    )
    baseline = IndicatorValues(rsi=50.0, rsi_ma=50.0, ema5=_BASELINE_EMA, ema20=_BASELINE_EMA)
    indicators = tuple(overrides.get(i, baseline) for i in range(SERIES_LENGTH))
    return CandleSeries(candles=candles, indicators=indicators)


def _kandidat_indikatoren() -> IndicatorValues:
    """Laesst RSI-Kreuz und EMA-Kreuz an derselben Kerze feuern."""
    return IndicatorValues(rsi=60.0, rsi_ma=50.0, ema5=110.0, ema20=_BASELINE_EMA)


class TestNutzlast:
    def test_ein_kandidat_traegt_seine_kriterien_und_die_episode(self) -> None:
        payload = build_chart_payload("TEST", _serie({20: _kandidat_indikatoren()}), PARAMS)
        kerze = payload["kerzen"][20]

        assert "gate" not in kerze
        assert kerze["first"] is True
        assert kerze["ep"] == 0
        assert "RSI_CROSS" in kerze["sig"]
        assert payload["treffer"] == 1
        assert payload["episoden"] == 1

    def test_ein_verworfener_punkt_traegt_seinen_grund(self) -> None:
        """Beide Kaufsignale liegen zwei Kerzen zurueck -- die Frische fehlt."""
        payload = build_chart_payload("TEST", _serie({18: _kandidat_indikatoren()}), PARAMS)
        kerze = payload["kerzen"][20]

        assert kerze["gate"] == "gate:stale_crossing_signals"
        # Die Signale bleiben sichtbar: Es soll ablesbar sein, was erfuellt war.
        assert "RSI_CROSS" in kerze["sig"]
        assert payload["verworfen"] >= 1
        # Kerze 18 selbst ist ein gueltiger Kandidat -- dort sind die Signale
        # frisch. Verworfen wird erst der Nachzuegler auf 20.
        assert payload["kerzen"][18].get("gate") is None

    def test_die_zweite_tageskerze_ist_kein_entscheidungspunkt(self) -> None:
        payload = build_chart_payload("TEST", _serie({21: _kandidat_indikatoren()}), PARAMS)

        assert "sig" not in payload["kerzen"][21]
        assert "gate" not in payload["kerzen"][21]

    def test_folgetrigger_derselben_episode_sind_als_solche_erkennbar(self) -> None:
        """Zwei Entscheidungspunkte auf geteilter Grundlage.

        Die Kreuzung feuert auf 20 und erneut auf 22. Punkt 22 sieht beide
        Feuerungen, teilt also die auf 20 mit dem ersten Punkt -- eine
        Episode, ein gezaehltes Ereignis, zwei Dreiecke. Genau diese
        Unterscheidung ist der Zweck des Charts, und sie ist der Grund, warum
        der Test die Werte einzeln nennt statt sie gegeneinander zu
        rechnen: Zwei abgeleitete Groessen koennen gemeinsam falsch sein.
        """
        payload = build_chart_payload(
            "TEST",
            _serie({20: _kandidat_indikatoren(), 22: _kandidat_indikatoren()}),
            PARAMS,
        )

        assert payload["kerzen"][20]["first"] is True
        assert payload["kerzen"][22]["first"] is False
        assert payload["kerzen"][20]["ep"] == payload["kerzen"][22]["ep"]
        assert payload["treffer"] == 2
        assert payload["episoden"] == 1

    def test_geprueft_zaehlt_nur_erste_tageskerzen(self) -> None:
        """``geprueft`` sind die ausgewerteten Kerzen, ``treffer`` die
        Entscheidungspunkte im Sinne von ADR 0057 -- zwei verschiedene
        Zahlen, die sich leicht verwechseln lassen."""
        payload = build_chart_payload("TEST", _serie(), PARAMS)
        erste_tageskerzen_nach_warmup = len(
            [i for i in range(PARAMS.warmup_candles, SERIES_LENGTH) if i % 2 == 0]
        )

        assert payload["geprueft"] == erste_tageskerzen_nach_warmup
        assert payload["treffer"] == 0

    def test_die_regelversion_steht_in_der_nutzlast(self) -> None:
        """Ein Chart ohne Regelversion liesse offen, welche Regel er zeigt."""
        payload = build_chart_payload("TEST", _serie(), PARAMS)
        assert payload["regelversion"].startswith("g1-pruefvorlage-")


class TestSeite:
    def test_die_seite_traegt_die_daten_in_sich(self) -> None:
        html = render_chart_html(build_chart_payload("TEST", _serie(), PARAMS))

        assert html.startswith("<!doctype html>")
        assert '<script id="daten"' in html
        assert '"symbol":"TEST"' in html
        assert "__DATEN__" not in html

    def test_die_seite_laedt_nichts_aus_dem_netz(self) -> None:
        """Der Server hat kein Internet -- ein Abruf bliebe leer, ohne dass
        es auffiele."""
        html = render_chart_html(build_chart_payload("TEST", _serie(), PARAMS))

        assert "http://" not in html
        assert "https://" not in html

    def test_ein_script_ende_in_den_daten_beendet_die_seite_nicht(self) -> None:
        html = render_chart_html(build_chart_payload("</script><b>x", _serie(), PARAMS))
        assert "</script><b>x" not in html
        assert "<\\/script>" in html
