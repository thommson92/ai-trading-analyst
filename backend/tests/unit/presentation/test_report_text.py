"""Die lesbare Fassung rendert das gespeicherte Dokument (ADR 0039).

Nicht die Domain-Objekte: Was auf der Konsole steht, ist damit genau das, was
in der Datenbank liegt -- und keine zweite Zusammenstellung, die davon
abweichen koennte.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.report import ReportSection, as_document, build_report
from ai_trading_analyst.presentation.report_text import render_report, render_run
from tests.unit.domain.report.conftest import (
    make_backtest,
    make_earnings,
    make_outcome,
    make_technical,
)

ERSTELLT = datetime(2026, 8, 30, 21, 5, tzinfo=UTC)


def dokument(**overrides: object) -> dict:  # type: ignore[type-arg]
    return as_document(
        build_report(make_outcome(**overrides), created_at=ERSTELLT, app_version="0.1.0")
    )


class TestVollstaendigkeit:
    def test_alle_achtzehn_abschnitte_erscheinen_in_der_ausgabe(self) -> None:
        text = render_report(dokument(), symbol="AAPL")
        for section in ReportSection:
            assert section.value in text, f"{section.value} fehlt in der lesbaren Fassung"

    def test_die_abschnitte_stehen_in_der_reihenfolge_von_doc_10(self) -> None:
        text = render_report(dokument(), symbol="AAPL")
        stellen = [text.index(section.value) for section in ReportSection]
        assert stellen == sorted(stellen)

    def test_ein_fehlender_punkt_wird_als_solcher_gekennzeichnet(self) -> None:
        text = render_report(dokument(), symbol="AAPL")
        zeilen = text.splitlines()
        (kopf,) = [z for z in zeilen if z.strip().startswith("14. SWING_SCORE")]
        assert "NICHT VERFUEGBAR" in kopf

    def test_jede_luecke_bringt_ihre_begruendung_mit(self) -> None:
        text = render_report(dokument(), symbol="AAPL")
        assert "[FEHLT] Optionsanalyse und Scoring gehoeren zu Sprint 5" in text


class TestInhalt:
    def test_der_kopf_nennt_die_versionen(self) -> None:
        text = render_report(dokument(), symbol="AAPL")
        assert "Bericht report-v1" in text
        assert "Anwendung 0.1.0" in text

    def test_vorbehalte_sind_von_luecken_unterscheidbar(self) -> None:
        text = render_report(
            dokument(
                backtest=(make_backtest(),),
                earnings=make_earnings(EarningsFilterStatus.UNKNOWN, "x"),
            ),
            symbol="AAPL",
        )
        assert "[EINGESCHRAENKT]" in text
        assert "[FEHLT]" in text

    def test_verschachtelte_werte_werden_eingerueckt(self) -> None:
        text = render_report(dokument(technical=make_technical()), symbol="AAPL")
        assert "  deterministisch:" in text
        assert "    close: 190.0" in text

    def test_leere_felder_erscheinen_nicht(self) -> None:
        """Ein Feld mit ``null`` daneben saehe aus wie ein Ergebnis, das
        null ist -- der Unterschied steht schon in den Vorbehalten."""
        text = render_report(dokument(technical=make_technical()), symbol="AAPL")
        assert ": None" not in text


class TestGanzerLauf:
    def test_ohne_berichte_sagt_die_ausgabe_das(self) -> None:
        assert "keine Kandidaten" in render_run([])

    def test_mehrere_berichte_werden_getrennt(self) -> None:
        text = render_run([("AAA", dokument()), ("BBB", dokument())])
        assert "=== AAA ===" in text
        assert "=== BBB ===" in text
