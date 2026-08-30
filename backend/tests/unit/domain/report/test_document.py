"""Das Dokument fuehrt immer alle achtzehn Abschnitte (ADR 0039).

Ein fehlender Punkt ist ein Abschnitt mit ``verfuegbar: false`` und einer
Begruendung -- nie ein weggelassener Schluessel. Genau das unterscheidet
"unvollstaendige Analyse" von "kuerzerer Bericht".
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from ai_trading_analyst.domain.earnings import EarningsFilterStatus
from ai_trading_analyst.domain.report import ReportSection, as_document, build_report
from tests.unit.domain.report.conftest import (
    make_backtest,
    make_earnings,
    make_fundamentals,
    make_outcome,
    make_research,
    make_technical,
)

ERSTELLT = datetime(2026, 8, 30, 21, 5, tzinfo=UTC)


def dokument(**overrides: object) -> dict:  # type: ignore[type-arg]
    report = build_report(
        make_outcome(**overrides), created_at=ERSTELLT, app_version="0.1.0"
    )
    return as_document(report)


def vollstaendig() -> dict:  # type: ignore[type-arg]
    return dokument(
        earnings=make_earnings(EarningsFilterStatus.EARNINGS_CLEAR),
        backtest=(make_backtest(),),
        technical=make_technical(),
        research=make_research(),
        fundamentals=make_fundamentals(vollstaendig=True),
    )


class TestAchtzehnAbschnitte:
    def test_der_karge_fall_fuehrt_trotzdem_alle_achtzehn(self) -> None:
        abschnitte = dokument()["abschnitte"]
        assert set(abschnitte) == {section.value for section in ReportSection}

    def test_der_vollstaendige_fall_fuehrt_dieselben_achtzehn(self) -> None:
        assert set(vollstaendig()["abschnitte"]) == {section.value for section in ReportSection}

    def test_die_nummern_folgen_doc_10(self) -> None:
        abschnitte = dokument()["abschnitte"]
        assert abschnitte[ReportSection.SYMBOL_UND_UNTERNEHMEN.value]["nummer"] == 1
        assert abschnitte[ReportSection.SIGNALSTATISTIK.value]["nummer"] == 5
        assert abschnitte[ReportSection.EMPFEHLUNG.value]["nummer"] == 16
        assert abschnitte[ReportSection.QUELLEN.value]["nummer"] == 18
        assert sorted(a["nummer"] for a in abschnitte.values()) == list(range(1, 19))

    def test_jeder_nicht_verfuegbare_abschnitt_nennt_einen_grund(self) -> None:
        for name, abschnitt in dokument()["abschnitte"].items():
            if not abschnitt["verfuegbar"]:
                assert abschnitt["vorbehalte"], f"{name} ohne Begruendung"
                assert abschnitt["inhalt"] is None, f"{name} hat Inhalt trotz Luecke"


class TestSerialisierbarkeit:
    def test_das_dokument_ist_json(self) -> None:
        """Die verbindliche Fassung geht als JSONB in die Datenbank. Ein Wert,
        der sich nicht schreiben laesst, faellt hier auf und nicht erst im
        Tageslauf."""
        json.dumps(vollstaendig())

    def test_zeitpunkte_werden_zu_iso_zeichenketten(self) -> None:
        dok = vollstaendig()
        assert dok["erstellt_am"] == ERSTELLT.isoformat()
        lage = dok["abschnitte"][ReportSection.TECHNISCHE_LAGE.value]["inhalt"]
        assert isinstance(lage["deterministisch"]["evaluated_at"], str)

    def test_mengen_werden_sortiert(self) -> None:
        """Sonst haengt das Dokument an der Hash-Reihenfolge, und zwei Laeufe
        mit demselben Inhalt ergaeben verschiedene Berichte."""
        statistik = vollstaendig()["abschnitte"][ReportSection.SIGNALSTATISTIK.value]["inhalt"]
        typen = statistik[0]["signal_types"]
        assert typen == sorted(typen)


class TestInhalte:
    def test_die_versionen_stehen_im_kopf(self) -> None:
        dok = dokument()
        assert dok["berichtsschema_version"] == "report-v1"
        assert dok["anwendungsversion"] == "0.1.0"
        assert dok["scoring_version"] is None

    def test_punkt_siebzehn_zaehlt_die_luecken_auf(self) -> None:
        inhalt = dokument()["abschnitte"][ReportSection.KONFIDENZ_UND_DATENLUECKEN.value]["inhalt"]
        abschnitte = {luecke["abschnitt"] for luecke in inhalt["luecken"]}
        assert ReportSection.SWING_SCORE.value in abschnitte
        assert ReportSection.PUT_STRATEGIEN.value in inhalt["fehlende_abschnitte"]

    def test_punkt_siebzehn_ist_selbst_nie_eine_luecke(self) -> None:
        """Der Abschnitt, der die Luecken aufzaehlt, hat immer Inhalt -- auch
        wenn alles andere fehlt."""
        abschnitt = dokument()["abschnitte"][ReportSection.KONFIDENZ_UND_DATENLUECKEN.value]
        assert abschnitt["verfuegbar"]
        assert abschnitt["inhalt"]["luecken"]

    def test_die_analystenmeinungen_fuehren_kursziele_als_leer(self) -> None:
        """Punkt 9 verlangt sie ausdruecklich. Sie fehlen -- und der Schluessel
        steht trotzdem da, damit niemand sie uebersieht (ADR 0017)."""
        inhalt = vollstaendig()["abschnitte"][ReportSection.ANALYSTENMEINUNGEN.value]["inhalt"]
        assert inhalt["kursziele"] is None

    def test_risiken_kommen_aus_beiden_modulen(self) -> None:
        inhalt = vollstaendig()["abschnitte"][ReportSection.RISIKEN.value]["inhalt"]
        assert "Lieferkette" in inhalt

    def test_die_fundamentalkennzahlen_stehen_vollstaendig_im_dokument(self) -> None:
        inhalt = vollstaendig()["abschnitte"][ReportSection.FUNDAMENTALE_BEWERTUNG.value]["inhalt"]
        assert inhalt["company_name"] == "Apple Inc."
        assert inhalt["metrics"]["REVENUE"]["sources"][0]["accession"]
