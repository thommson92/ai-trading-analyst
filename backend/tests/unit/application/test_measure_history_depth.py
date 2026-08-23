"""Die Tiefenmessung fuer die offene Entscheidung E2.

Geprueft wird das, worauf die Entscheidung sich stuetzt: dass sich die
Messung tatsaechlich zurueckarbeitet, dass sie unter allen Umstaenden endet,
und vor allem, dass sie eine **abgebrochene** Messung nicht als gemessene
Tiefe ausgibt.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from ai_trading_analyst.application.measure_history_depth import (
    DepthLimit,
    MeasureHistoryDepthUseCase,
)
from ai_trading_analyst.domain.analysis import ContractSpec, MarketDataProviderError
from ai_trading_analyst.domain.screening import IntradayBar

JETZT = datetime(2026, 8, 23, 20, 0, tzinfo=UTC)
AAPL = ContractSpec(symbol="AAPL")


def bar(start: datetime) -> IntradayBar:
    return IntradayBar(start=start, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)


class FakeWindowSource:
    """Eine Historie fester Tiefe, in Fenstern herausgegeben.

    ``depth_days`` ist die Tiefe, die dieser Anbieter hat: Anfragen darueber
    hinaus werden leer beantwortet -- genau wie IBKR am Ende seiner Historie.
    """

    def __init__(self, depth_days: int, now: datetime = JETZT) -> None:
        self._earliest = now - timedelta(days=depth_days)
        self._now = now
        self.calls: list[tuple[str, datetime | None, int]] = []

    def fetch_window(
        self, contract: ContractSpec, end: datetime | None, days: int
    ) -> Sequence[IntradayBar]:
        self.calls.append((contract.symbol, end, days))
        oberer_rand = end if end is not None else self._now
        unterer_rand = max(oberer_rand - timedelta(days=days), self._earliest)
        if unterer_rand >= oberer_rand:
            return ()
        # Zwei Bars je Fenster genuegen: Gemessen wird an den Raendern.
        return (bar(unterer_rand), bar(oberer_rand - timedelta(minutes=15)))

    def close(self) -> None:
        pass


class EndlessWindowSource:
    """Ein Anbieter, der nie leer antwortet -- der Fall fuer die Reissleine."""

    def __init__(self) -> None:
        self.calls = 0

    def fetch_window(
        self, contract: ContractSpec, end: datetime | None, days: int
    ) -> Sequence[IntradayBar]:
        self.calls += 1
        oberer_rand = end if end is not None else JETZT
        return (bar(oberer_rand - timedelta(days=days)), bar(oberer_rand))

    def close(self) -> None:
        pass


class StuckWindowSource:
    """Antwortet immer mit demselben Fenster, kommt also nicht zurueck."""

    def fetch_window(
        self, contract: ContractSpec, end: datetime | None, days: int
    ) -> Sequence[IntradayBar]:
        return (bar(JETZT - timedelta(days=400)), bar(JETZT - timedelta(days=1)))

    def close(self) -> None:
        pass


class FailingWindowSource:
    """Faellt bei einer Aktie im zweiten Fenster aus, die andere laeuft durch."""

    def __init__(self, failing_symbol: str) -> None:
        self._failing = failing_symbol
        self._calls: dict[str, int] = {}

    def fetch_window(
        self, contract: ContractSpec, end: datetime | None, days: int
    ) -> Sequence[IntradayBar]:
        gezaehlt = self._calls[contract.symbol] = self._calls.get(contract.symbol, 0) + 1
        if contract.symbol == self._failing and gezaehlt > 1:
            raise MarketDataProviderError("TWS weg")
        return FakeWindowSource(depth_days=800).fetch_window(contract, end, days)

    def close(self) -> None:
        pass


def use_case(source: object, **kwargs: int) -> MeasureHistoryDepthUseCase:
    return MeasureHistoryDepthUseCase(
        source,  # type: ignore[arg-type]
        now=lambda: JETZT,
        **kwargs,
    )


class TestTiefenmessung:
    def test_arbeitet_sich_fenster_fuer_fenster_zurueck(self) -> None:
        source = FakeWindowSource(depth_days=800)

        bericht = use_case(source, window_days=365).execute((AAPL,), bar_minutes=15)

        (ergebnis,) = bericht.results
        assert ergebnis.limit is DepthLimit.PROVIDER_EXHAUSTED
        # Das erste Fenster endet jetzt, jedes weitere frueher als das davor.
        assert source.calls[0][1] is None
        raender = [ruf[1] for ruf in source.calls[1:] if ruf[1] is not None]
        assert len(raender) == len(source.calls) - 1
        assert raender == sorted(raender, reverse=True)
        assert len(raender) >= 2
        assert all(ruf[2] == 365 for ruf in source.calls)

    def test_meldet_die_gemessene_tiefe(self) -> None:
        source = FakeWindowSource(depth_days=800)

        bericht = use_case(source, window_days=365).execute((AAPL,), bar_minutes=15)

        (ergebnis,) = bericht.results
        assert ergebnis.earliest == JETZT - timedelta(days=800)
        assert ergebnis.depth_days(JETZT) == 800
        assert ergebnis.is_lower_bound is False

    def test_reissleine_weist_die_tiefe_als_untergrenze_aus(self) -> None:
        source = EndlessWindowSource()

        bericht = use_case(source, window_days=365, maximum_windows=3).execute(
            (AAPL,), bar_minutes=15
        )

        (ergebnis,) = bericht.results
        assert source.calls == 3
        assert ergebnis.limit is DepthLimit.WINDOW_LIMIT
        assert ergebnis.is_lower_bound is True

    def test_kein_fortschritt_beendet_die_messung(self) -> None:
        bericht = use_case(StuckWindowSource(), maximum_windows=50).execute((AAPL,), bar_minutes=15)

        (ergebnis,) = bericht.results
        assert ergebnis.limit is DepthLimit.NO_PROGRESS
        assert ergebnis.windows == 2
        assert ergebnis.is_lower_bound is False

    def test_ein_ausfall_beendet_den_lauf_nicht(self) -> None:
        source = FailingWindowSource(failing_symbol="AAPL")

        bericht = use_case(source).execute((AAPL, ContractSpec(symbol="MSFT")), bar_minutes=15)

        gescheitert, durchgelaufen = bericht.results
        assert gescheitert.limit is DepthLimit.ERROR
        assert gescheitert.error is not None and "TWS weg" in gescheitert.error
        # Das bis zum Ausfall Erreichte bleibt erhalten -- als Untergrenze.
        assert gescheitert.earliest is not None
        assert gescheitert.is_lower_bound is True
        assert durchgelaufen.limit is DepthLimit.PROVIDER_EXHAUSTED
        assert bericht.failures == (gescheitert,)

    def test_ohne_bars_bleibt_die_tiefe_unbestimmt(self) -> None:
        source = FakeWindowSource(depth_days=0)

        bericht = use_case(source).execute((AAPL,), bar_minutes=15)

        (ergebnis,) = bericht.results
        assert ergebnis.limit is DepthLimit.PROVIDER_EXHAUSTED
        assert ergebnis.earliest is None
        assert ergebnis.depth_days(JETZT) is None
        assert bericht.shallowest is None

    def test_flachste_aktie_bestimmt_die_aussage(self) -> None:
        class ZweiTiefen:
            def fetch_window(
                self, contract: ContractSpec, end: datetime | None, days: int
            ) -> Sequence[IntradayBar]:
                tiefe = 800 if contract.symbol == "AAPL" else 300
                return FakeWindowSource(depth_days=tiefe).fetch_window(contract, end, days)

            def close(self) -> None:
                pass

        bericht = use_case(ZweiTiefen()).execute((AAPL, ContractSpec(symbol="NEU")), bar_minutes=15)

        flachste = bericht.shallowest
        assert flachste is not None
        assert flachste.symbol == "NEU"
        assert flachste.depth_days(JETZT) == 300

    def test_bericht_haelt_den_messrahmen_fest(self) -> None:
        bericht = use_case(FakeWindowSource(depth_days=400), window_days=90).execute(
            (AAPL,), bar_minutes=15
        )

        assert bericht.bar_minutes == 15
        assert bericht.window_days == 90
        assert bericht.measured_at == JETZT
