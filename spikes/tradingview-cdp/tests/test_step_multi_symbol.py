from __future__ import annotations

import pytest

from tvcdp.cdp_client import CdpSession
from tvcdp.steps import step_multi_symbol
from tvcdp.steps.base import StepStatus, run_step

from .conftest import JsError, ScriptedCdpServer


class TestStepMultiSymbol:
    async def test_keine_symbole_gilt_als_inconclusive(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        _, session = scripted_session

        result = await run_step(
            step_multi_symbol.STEP_ID,
            step_multi_symbol.TITLE,
            lambda: step_multi_symbol.run(session, [], "changeSymbol('{symbol}')", None),
        )

        assert result.status is StepStatus.INCONCLUSIVE

    async def test_keine_sonde_konfiguriert_gilt_als_inconclusive(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        _, session = scripted_session

        result = await run_step(
            step_multi_symbol.STEP_ID,
            step_multi_symbol.TITLE,
            lambda: step_multi_symbol.run(session, ["AAPL"], None, None),
        )

        assert result.status is StepStatus.INCONCLUSIVE

    async def test_alle_symbole_erfolgreich_gilt_als_passed_mit_performance_kennzahlen(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        for symbol in ("AAPL", "MSFT", "TSLA"):
            server.when(f"changeSymbol('{symbol}')", True)

        result = await run_step(
            step_multi_symbol.STEP_ID,
            step_multi_symbol.TITLE,
            lambda: step_multi_symbol.run(
                session, ["AAPL", "MSFT", "TSLA"], "changeSymbol('{symbol}')", None
            ),
        )

        assert result.status is StepStatus.PASSED
        perf = result.details["performance"]
        assert perf["symbol_count"] == 3
        assert perf["error_count"] == 0
        assert perf["error_rate"] == 0.0
        assert "average_seconds" in perf
        assert "median_seconds" in perf
        assert "slowest_seconds" in perf

    async def test_ein_fehlschlagendes_symbol_stoppt_die_uebrigen_nicht(
        self, scripted_session: tuple[ScriptedCdpServer, CdpSession]
    ) -> None:
        server, session = scripted_session
        server.when("changeSymbol('AAPL')", True)
        # MSFT bewusst nicht registriert -> evaluate() wirft
        server.when("changeSymbol('TSLA')", True)

        result = await run_step(
            step_multi_symbol.STEP_ID,
            step_multi_symbol.TITLE,
            lambda: step_multi_symbol.run(
                session, ["AAPL", "MSFT", "TSLA"], "changeSymbol('{symbol}')", None
            ),
        )

        assert result.status is StepStatus.INCONCLUSIVE
        per_symbol = {entry["symbol"]: entry for entry in result.details["per_symbol"]}
        assert per_symbol["AAPL"]["succeeded"] is True
        assert per_symbol["MSFT"]["succeeded"] is False
        assert "error" in per_symbol["MSFT"]
        assert per_symbol["TSLA"]["succeeded"] is True
        assert result.details["performance"]["error_count"] == 1

    @staticmethod
    def _no_wait_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
        """Ersetzt asyncio.sleep durch ein No-op, damit Polling-Tests nicht
        tatsaechlich Wandzeit verbrauchen -- der Zeitablauf fuer die
        Timeout-Erkennung selbst kommt weiterhin aus time.monotonic()."""

        async def _fake_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr("tvcdp.steps.step_multi_symbol.asyncio.sleep", _fake_sleep)

    async def test_erstes_symbol_wird_gegen_ausgangswert_vor_dem_wechsel_geprueft(
        self,
        scripted_session: tuple[ScriptedCdpServer, CdpSession],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Regression (dritte Iteration): eine neue CDP-Session zeigte auf dem
        Windows-Zielserver noch den Altbestand des zuletzt in einem frueheren
        Prozess gesetzten Symbols. Ohne einen Ausgangswert *vor* dem ersten
        Wechsel wuerde dieser Altbestand ungeprueft als Wert des ersten
        Symbols akzeptiert (nichts zum Vergleichen vorhanden -- ``None``
        unterscheidet sich immer von einem echten Wert)."""
        server, session = scripted_session
        self._no_wait_sleep(monkeypatch)
        server.when("changeSymbol('AAPL')", True)
        server.when("readValues()", {"rsi": 99})  # Ausgangswert: Altbestand, frueherer Lauf
        server.when("readValues()", {"rsi": 99})  # erster Poll-Versuch: noch nicht umgeschaltet
        server.when("readValues()", {"rsi": 1})  # zweiter Poll-Versuch: tatsaechlich AAPL

        result = await run_step(
            step_multi_symbol.STEP_ID,
            step_multi_symbol.TITLE,
            lambda: step_multi_symbol.run(
                session, ["AAPL"], "changeSymbol('{symbol}')", "readValues()", 5.0
            ),
        )

        assert result.status is StepStatus.PASSED
        entry = result.details["per_symbol"][0]
        assert entry["symbol_switch_verified"] is True
        assert entry["values"] == {"rsi": 1}
        # Ausgangslesung + zwei Poll-Versuche.
        assert server.received_expressions.count("readValues()") == 3

    async def test_liest_werte_erst_wenn_sie_sich_vom_vorherigen_symbol_unterscheiden(
        self,
        scripted_session: tuple[ScriptedCdpServer, CdpSession],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Regression (zweite Iteration): getSymbol() als Bereitschaftssignal
        erwies sich auf dem Windows-Zielserver als nutzlos -- es aktualisiert
        sich synchron mit dem Wechsel-Aufruf, unabhaengig davon, ob die
        Study-Daten schon nachgezogen sind. Stattdessen wird auf den
        tatsaechlichen Ruecklesewert gepollt, bis er sich vom vorherigen
        Wert unterscheidet."""
        server, session = scripted_session
        self._no_wait_sleep(monkeypatch)
        server.when("changeSymbol('AAPL')", True)
        server.when("changeSymbol('MSFT')", True)
        server.when("readValues()", {"rsi": 0})  # Ausgangswert vor dem ersten Wechsel
        server.when("readValues()", {"rsi": 1})  # AAPL: unterscheidet sich sofort vom Ausgangswert
        # Fuer MSFT liefert der erste Versuch noch den (AAPL-)Wert, erst der
        # zweite Versuch den tatsaechlich neuen Wert.
        server.when("readValues()", {"rsi": 1})
        server.when("readValues()", {"rsi": 2})

        result = await run_step(
            step_multi_symbol.STEP_ID,
            step_multi_symbol.TITLE,
            lambda: step_multi_symbol.run(
                session, ["AAPL", "MSFT"], "changeSymbol('{symbol}')", "readValues()", 5.0
            ),
        )

        assert result.status is StepStatus.PASSED
        per_symbol = {entry["symbol"]: entry for entry in result.details["per_symbol"]}
        assert per_symbol["AAPL"]["values"] == {"rsi": 1}
        assert per_symbol["MSFT"]["symbol_switch_verified"] is True
        assert per_symbol["MSFT"]["values"] == {"rsi": 2}
        # Ausgangslesung + AAPL (1 Versuch) + MSFT (2 Versuche).
        assert server.received_expressions.count("readValues()") == 4

    async def test_transiente_js_fehler_waehrend_des_uebergangs_gelten_als_noch_nicht_bereit(
        self,
        scripted_session: tuple[ScriptedCdpServer, CdpSession],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Regression: im echten 10-Symbol-Testlauf warfen mehrere Symbole
        'Cannot read properties of undefined' beim Lesen der Werte, weil die
        Studies waehrend des Symbolwechsels voruebergehend neu aufgebaut
        werden. Das darf nicht als endgueltiger Fehlschlag gelten, solange
        innerhalb des Timeouts noch ein gueltiger Wert ankommt."""
        server, session = scripted_session
        self._no_wait_sleep(monkeypatch)
        server.when("changeSymbol('NVDA')", True)
        server.when("readValues()", {"rsi": 0})  # Ausgangswert vor dem Wechsel
        server.when("readValues()", JsError("Cannot read properties of undefined"))
        server.when("readValues()", {"rsi": 3})

        result = await run_step(
            step_multi_symbol.STEP_ID,
            step_multi_symbol.TITLE,
            lambda: step_multi_symbol.run(
                session, ["NVDA"], "changeSymbol('{symbol}')", "readValues()", 5.0
            ),
        )

        assert result.status is StepStatus.PASSED
        assert result.details["per_symbol"][0]["values"] == {"rsi": 3}
        # Ausgangslesung + ein fehlerhafter Poll-Versuch + ein erfolgreicher.
        assert server.received_expressions.count("readValues()") == 3

    async def test_nie_bestaetigter_wert_fuehrt_zu_fehlschlag_statt_veraltetem_wert(
        self,
        scripted_session: tuple[ScriptedCdpServer, CdpSession],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Regression: auf dem Windows-Zielserver blieben mehrere Symbole
        trotz Wartezeit auf dem Wert eines vorherigen Symbols haengen -- ohne
        jeden Fehler, nur mit einem falschen (identischen) Wert. Bleibt der
        Wert unveraendert, bis das Timeout erreicht ist, darf er nicht als
        Ergebnis gemeldet werden."""
        server, session = scripted_session
        self._no_wait_sleep(monkeypatch)
        server.when("changeSymbol('AAPL')", True)
        server.when("changeSymbol('TSLA')", True)
        server.when("readValues()", {"rsi": 0})  # Ausgangswert, unterscheidet sich von AAPL
        server.when("readValues()", {"rsi": 42})  # AAPL: einmalig, danach dauerhaft wiederholt

        result = await run_step(
            step_multi_symbol.STEP_ID,
            step_multi_symbol.TITLE,
            lambda: step_multi_symbol.run(
                session, ["AAPL", "TSLA"], "changeSymbol('{symbol}')", "readValues()", 0.05
            ),
        )

        assert result.status is StepStatus.INCONCLUSIVE
        per_symbol = {entry["symbol"]: entry for entry in result.details["per_symbol"]}
        assert per_symbol["AAPL"]["succeeded"] is True
        entry = per_symbol["TSLA"]
        assert entry["succeeded"] is False
        assert entry["symbol_switch_verified"] is False
        assert "values" not in entry
        assert "nicht bestaetigt" in entry["error"]

    async def test_ohne_timeout_werden_werte_ungeprueft_gelesen(
        self,
        scripted_session: tuple[ScriptedCdpServer, CdpSession],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Ohne switch_timeout_seconds > 0 kann der Schritt einen Wechsel nur
        ausloesen, nicht verifizieren -- das wird sichtbar gemacht
        (symbol_switch_verified: None), statt den Wert stillschweigend als
        korrekt zu behandeln."""
        server, session = scripted_session
        self._no_wait_sleep(monkeypatch)
        server.when("changeSymbol('AAPL')", True)
        server.when("readValues()", {"rsi": 42})

        result = await run_step(
            step_multi_symbol.STEP_ID,
            step_multi_symbol.TITLE,
            lambda: step_multi_symbol.run(
                session, ["AAPL"], "changeSymbol('{symbol}')", "readValues()"
            ),
        )

        assert result.status is StepStatus.PASSED
        entry = result.details["per_symbol"][0]
        assert entry["symbol_switch_verified"] is None
        assert entry["values"] == {"rsi": 42}
