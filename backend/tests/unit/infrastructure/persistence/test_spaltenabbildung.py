"""Die Spaltenabbildungen von Chartauswertung und KI-Einordnung.

Beide Helfer haben zwei Zweige: einen fuer "liegt vor" und einen fuer "liegt
nicht vor". Der leere Zweig baut die Schluessel aus einer Tupelkonstante, der
gefuellte aus einem Literal. Laufen sie auseinander, bleibt beim
Wiederverwenden einer Zeile ein alter Wert stehen (fehlender Schluessel) oder
``ScreeningResultOrm(**kwargs)`` scheitert mit ``TypeError`` (ueberzaehliger
Schluessel). Beides faellt sonst erst in der Datenbank auf.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ai_trading_analyst.domain.technical import (
    TechnicalAssessment,
    TechnicalAssessmentStatus,
    TechnicalSnapshot,
    TechnicalStatus,
)
from ai_trading_analyst.infrastructure.persistence.orm import ScreeningResultOrm
from ai_trading_analyst.infrastructure.persistence.repositories import (
    _technical_ai_columns,
    _technical_columns,
)

EVALUATED_AT = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)

_SNAPSHOT = TechnicalSnapshot(
    status=TechnicalStatus.COMPLETED, evaluated_at=EVALUATED_AT, close=100.0
)
_ASSESSMENT = TechnicalAssessment(
    status=TechnicalAssessmentStatus.COMPLETED,
    evaluated_at=EVALUATED_AT,
    model="fixture",
    prompt_version="fixture-v1",
)


def _spalten_der_tabelle(praefix: str) -> set[str]:
    return {
        spalte.name
        for spalte in ScreeningResultOrm.__table__.columns
        if spalte.name.startswith(praefix)
    }


class TestChartauswertung:
    def test_beide_zweige_liefern_dieselben_schluessel(self) -> None:
        assert set(_technical_columns(None)) == set(_technical_columns(_SNAPSHOT))

    def test_die_spalten_decken_sich_genau(self) -> None:
        """Gleichheit statt Teilmenge: Eine ORM-Spalte mit demselben Praefix,
        die nie geschrieben wird, faellt sonst nicht auf."""
        gesetzt = set(_technical_columns(_SNAPSHOT))
        # ``technical_ai_`` traegt denselben Anfang und gehoert nicht dazu.
        assert gesetzt == _spalten_der_tabelle("technical_") - _spalten_der_tabelle(
            "technical_ai_"
        )

    def test_ohne_auswertung_wird_jede_spalte_ausdruecklich_geleert(self) -> None:
        assert all(wert is None for wert in _technical_columns(None).values())


class TestKiEinordnung:
    def test_beide_zweige_liefern_dieselben_schluessel(self) -> None:
        assert set(_technical_ai_columns(None)) == set(_technical_ai_columns(_ASSESSMENT))

    def test_die_spalten_decken_sich_genau(self) -> None:
        assert set(_technical_ai_columns(_ASSESSMENT)) == _spalten_der_tabelle("technical_ai_")

    def test_ohne_einordnung_wird_jede_spalte_ausdruecklich_geleert(self) -> None:
        assert all(wert is None for wert in _technical_ai_columns(None).values())

    def test_die_beiden_spaltensaetze_ueberschneiden_sich_nicht(self) -> None:
        """Doc 10, Paragraph 6.8 verlangt getrennte Speicherung. Eine
        gemeinsame Spalte waere die Stelle, an der die Trennung stillschweigend
        aufginge."""
        assert not set(_technical_columns(_SNAPSHOT)) & set(_technical_ai_columns(_ASSESSMENT))
