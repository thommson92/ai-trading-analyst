"""Die Aufloesung von ``companyfacts`` (ADR 0032).

Die Beispiele sind bewusst am echten Format gebaut, aber klein: Jeder Fall
hier steht fuer einen Befund, der beim Lauf gegen echte Einreichungen
aufgetreten ist.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from ai_trading_analyst.domain.fundamentals import FigureName
from ai_trading_analyst.infrastructure.edgar.companyfacts import (
    FIGURE_TAGS,
    CompanyFactsError,
    resolve_company_facts,
)


def _fakt(
    val: float,
    *,
    start: str | None,
    end: str,
    accn: str = "0000000000-24-000001",
    form: str = "10-K",
    filed: str = "2024-11-01",
) -> dict[str, Any]:
    eintrag: dict[str, Any] = {"val": val, "end": end, "accn": accn, "form": form, "filed": filed}
    if start is not None:
        eintrag["start"] = start
    return eintrag


def _antwort(us_gaap: dict[str, Any], dei: dict[str, Any] | None = None) -> dict[str, Any]:
    facts: dict[str, Any] = {"us-gaap": us_gaap}
    if dei is not None:
        facts["dei"] = dei
    return {"cik": 320193, "entityName": "Test Inc.", "facts": facts}


def _usd(*fakten: dict[str, Any]) -> dict[str, Any]:
    return {"units": {"USD": list(fakten)}}


class TestStruktur:
    def test_eine_antwort_ohne_us_gaap_ist_ein_fehler(self) -> None:
        """Ein leeres Ergebnis waere nicht von einem Unternehmen ohne
        Einreichungen zu unterscheiden -- IFRS-Berichte per 20-F fallen
        hierunter (ADR 0032 L3)."""
        with pytest.raises(CompanyFactsError, match="us-gaap"):
            resolve_company_facts({"cik": 1, "entityName": "X", "facts": {"ifrs-full": {}}})

    def test_eine_unvollstaendige_antwort_ist_ein_fehler(self) -> None:
        with pytest.raises(CompanyFactsError, match="unvollstaendig"):
            resolve_company_facts({"cik": 1})


class TestJahreswerte:
    def test_quartalszahlen_fallen_heraus(self) -> None:
        """Ein 10-K enthaelt auch Quartalswerte. Ohne die Dauerpruefung
        liefe eine Jahresumsatzreihe still mit einzelnen Quartalen darin."""
        antwort = _antwort(
            {
                "Revenues": _usd(
                    _fakt(100.0, start="2024-01-01", end="2024-03-31"),
                    _fakt(400.0, start="2024-01-01", end="2024-12-31"),
                )
            }
        )
        umsaetze = resolve_company_facts(antwort).figures[FigureName.REVENUE]
        assert [figure.value for figure in umsaetze] == [400.0]

    def test_nur_jahresabschluesse_und_ihre_aenderungsberichte(self) -> None:
        antwort = _antwort(
            {
                "Revenues": _usd(
                    _fakt(400.0, start="2023-01-01", end="2023-12-31", form="10-Q"),
                    _fakt(500.0, start="2024-01-01", end="2024-12-31", form="10-K/A"),
                )
            }
        )
        umsaetze = resolve_company_facts(antwort).figures[FigureName.REVENUE]
        assert [figure.period_end for figure in umsaetze] == [date(2024, 12, 31)]

    def test_bestandsgroessen_haben_keinen_zeitraum(self) -> None:
        """Wuerde man sie wie Zeitraumgroessen behandeln, fielen sie durch die
        Dauerpruefung und alle Bilanzkennzahlen fehlten -- ohne Fehler."""
        antwort = _antwort({"Assets": _usd(_fakt(1000.0, start=None, end="2024-12-31"))})
        vermoegen = resolve_company_facts(antwort).figures[FigureName.ASSETS]
        assert vermoegen[0].period_start is None
        assert vermoegen[0].value == 1000.0


class TestNeuausweise:
    def test_die_zuletzt_eingereichte_angabe_gewinnt(self) -> None:
        """426 solcher Zeitraeume allein bei Apple. Ohne diese Regel haengt
        das Ergebnis an der Reihenfolge im JSON."""
        antwort = _antwort(
            {
                "Revenues": _usd(
                    _fakt(
                        400.0,
                        start="2023-01-01",
                        end="2023-12-31",
                        accn="alt",
                        filed="2024-02-01",
                    ),
                    _fakt(
                        380.0,
                        start="2023-01-01",
                        end="2023-12-31",
                        accn="neu",
                        filed="2025-02-01",
                    ),
                )
            }
        )
        umsatz = resolve_company_facts(antwort).figures[FigureName.REVENUE][0]
        assert umsatz.value == 380.0
        assert umsatz.source.accession == "neu"

    def test_die_reihenfolge_im_json_aendert_nichts(self) -> None:
        antwort = _antwort(
            {
                "Revenues": _usd(
                    _fakt(380.0, start="2023-01-01", end="2023-12-31", filed="2025-02-01"),
                    _fakt(400.0, start="2023-01-01", end="2023-12-31", filed="2024-02-01"),
                )
            }
        )
        assert resolve_company_facts(antwort).figures[FigureName.REVENUE][0].value == 380.0


class TestTagReihenfolge:
    def test_das_erste_tag_der_liste_gewinnt(self) -> None:
        """``Revenues`` steht vorn, weil es die Gesamtzeile ist: Bei
        Berkshire traegt das Vertragsumsatz-Tag 41 bis 47 Prozent weniger."""
        antwort = _antwort(
            {
                "Revenues": _usd(_fakt(1000.0, start="2024-01-01", end="2024-12-31")),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _usd(
                    _fakt(560.0, start="2024-01-01", end="2024-12-31")
                ),
            }
        )
        aufgeloest = resolve_company_facts(antwort)
        assert aufgeloest.figures[FigureName.REVENUE][0].value == 1000.0

    def test_ein_widerspruch_wird_gemeldet_statt_verschwiegen(self) -> None:
        antwort = _antwort(
            {
                "Revenues": _usd(_fakt(1000.0, start="2024-01-01", end="2024-12-31")),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _usd(
                    _fakt(560.0, start="2024-01-01", end="2024-12-31")
                ),
            }
        )
        konflikte = resolve_company_facts(antwort).conflicts
        assert len(konflikte) == 1
        assert konflikte[0].figure is FigureName.REVENUE
        assert konflikte[0].chosen_value == 1000.0
        assert konflikte[0].relative_deviation == pytest.approx(0.44)

    def test_gleiche_werte_sind_kein_widerspruch(self) -> None:
        """Bei NVIDIA decken sich beide Umsatz-Tags in acht Zeitraeumen auf
        den Cent -- daraus jedes Mal eine Meldung zu machen waere Laerm."""
        antwort = _antwort(
            {
                "Revenues": _usd(_fakt(1000.0, start="2024-01-01", end="2024-12-31")),
                "SalesRevenueNet": _usd(_fakt(1000.0, start="2024-01-01", end="2024-12-31")),
            }
        )
        assert resolve_company_facts(antwort).conflicts == ()

    def test_ein_nachrangiges_tag_fuellt_eine_luecke(self) -> None:
        """Apple hat ``Revenues`` nach 2018 aufgegeben. Ohne den Rueckgriff
        auf das naechste Tag brechen alle Reihen dort ab."""
        antwort = _antwort(
            {
                "Revenues": _usd(_fakt(800.0, start="2023-01-01", end="2023-12-31")),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _usd(
                    _fakt(900.0, start="2024-01-01", end="2024-12-31")
                ),
            }
        )
        umsaetze = resolve_company_facts(antwort).figures[FigureName.REVENUE]
        assert [figure.value for figure in umsaetze] == [800.0, 900.0]


class TestZwoelfmonatswert:
    """ADR 0033, Entscheidung 1 und 2."""

    def _reihe(self, jahr_wert: float, teil_wert: float, vor_wert: float, *, jahr: int,
               accn: str = "0000000000-26-000001") -> dict[str, Any]:
        """Jahresabschluss, laufendes Halbjahr und Vorjahres-Halbjahr."""
        return _usd(
            _fakt(jahr_wert, start=f"{jahr}-01-01", end=f"{jahr}-12-31"),
            _fakt(vor_wert, start=f"{jahr}-01-01", end=f"{jahr}-06-30"),
            _fakt(teil_wert, start=f"{jahr + 1}-01-01", end=f"{jahr + 1}-06-30",
                  accn=accn, form="10-Q", filed=f"{jahr + 1}-08-01"),
        )

    def test_die_formel_verrechnet_nur_ausgewiesene_zeitraeume(self) -> None:
        """Jahr + laufendes Teilstueck - Vorjahresteilstueck. Nie werden zwei
        Zeitraeume zu einem laengeren zusammengefasst -- das umgeht die
        Verwechslung von kumulierten und diskreten Quartalen."""
        antwort = _antwort({"Revenues": self._reihe(1000.0, 600.0, 500.0, jahr=2025)})
        zwoelf = resolve_company_facts(antwort).trailing[FigureName.REVENUE]
        assert zwoelf.value == pytest.approx(1100.0)
        assert zwoelf.period_end == date(2026, 6, 30)

    def test_ohne_vorjahresstueck_gibt_es_keinen_zwoelfmonatswert(self) -> None:
        antwort = _antwort(
            {
                "Revenues": _usd(
                    _fakt(1000.0, start="2025-01-01", end="2025-12-31"),
                    _fakt(600.0, start="2026-01-01", end="2026-06-30", form="10-Q"),
                )
            }
        )
        assert FigureName.REVENUE not in resolve_company_facts(antwort).trailing

    def test_das_juengste_fenster_gewinnt_nicht_das_erste_tag(self) -> None:
        """Gemessen an Honeywell: ``Revenues`` endet dort 2011. Nach blosser
        Tag-Reihenfolge entstand ein Zwoelfmonatsumsatz per 2012 -- vierzehn
        Jahre alt, aus einem laengst aufgegebenen Tag."""
        antwort = _antwort(
            {
                "Revenues": self._reihe(100.0, 60.0, 50.0, jahr=2011, accn="alt"),
                "RevenueFromContractWithCustomerExcludingAssessedTax": self._reihe(
                    1000.0, 600.0, 500.0, jahr=2025
                ),
            }
        )
        zwoelf = resolve_company_facts(antwort).trailing[FigureName.REVENUE]
        assert zwoelf.period_end == date(2026, 6, 30)
        assert zwoelf.value == pytest.approx(1100.0)

    def test_bei_gleichem_ende_entscheidet_die_tag_reihenfolge(self) -> None:
        """Dann geht es wieder um die Bedeutung, nicht um die Aktualitaet --
        und ``Revenues`` ist die Gesamtzeile."""
        antwort = _antwort(
            {
                "Revenues": self._reihe(1000.0, 600.0, 500.0, jahr=2025),
                "RevenueFromContractWithCustomerExcludingAssessedTax": self._reihe(
                    700.0, 420.0, 350.0, jahr=2025, accn="andere"
                ),
            }
        )
        zwoelf = resolve_company_facts(antwort).trailing[FigureName.REVENUE]
        assert zwoelf.source.tag == "Revenues"

    def test_bestandsgroessen_bekommen_keinen_zwoelfmonatswert(self) -> None:
        """Sie gelten zu einem Stichtag; ein Fenster daraus waere sinnlos."""
        antwort = _antwort(
            {
                "Revenues": self._reihe(1000.0, 600.0, 500.0, jahr=2025),
                "Assets": _usd(_fakt(5000.0, start=None, end="2026-06-30", form="10-Q")),
            }
        )
        aufgeloest = resolve_company_facts(antwort)
        assert FigureName.ASSETS not in aufgeloest.trailing
        assert aufgeloest.figures[FigureName.ASSETS][0].period_end == date(2026, 6, 30)


class TestTagListenSindBedeutungsgleich:
    """ADR 0032, Entscheidung 2 -- die Regel, an der drei eigene Listen
    scheiterten, als sie zum ersten Mal auf echte Filings trafen."""

    @pytest.mark.parametrize(
        "tag",
        [
            "SalesRevenueGoodsNet",
            "ProfitLoss",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ],
    )
    def test_tags_mit_anderer_bedeutung_stehen_in_keiner_liste(self, tag: str) -> None:
        alle = {eintrag for tags in FIGURE_TAGS.values() for eintrag in tags}
        assert tag not in alle


class TestUnbrauchbareEintraege:
    def test_ein_unlesbarer_fakt_kostet_nicht_die_ganze_aktie(self) -> None:
        """``companyfacts`` fuehrt hunderte Tags. Ein Formatfehler in einem
        davon darf nicht den ganzen Emittenten unauswertbar machen."""
        antwort = _antwort(
            {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"val": "kaputt", "end": "2024-12-31"},
                            _fakt(1000.0, start="2024-01-01", end="2024-12-31"),
                        ]
                    }
                }
            }
        )
        assert resolve_company_facts(antwort).figures[FigureName.REVENUE][0].value == 1000.0


class TestAktienzahl:
    def test_der_spaeteste_stichtag_gewinnt(self) -> None:
        """Nicht die spaeteste Einreichung: Ein Aenderungsbericht kann heute
        eingereicht werden und einen alten Stichtag tragen."""
        antwort = _antwort(
            {"Revenues": _usd(_fakt(1.0, start="2024-01-01", end="2024-12-31"))},
            dei={
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            _fakt(90.0, start=None, end="2026-07-17", filed="2026-07-31"),
                            _fakt(99.0, start=None, end="2020-01-01", filed="2026-08-01"),
                        ]
                    }
                }
            },
        )
        aktien = resolve_company_facts(antwort).shares_outstanding
        assert aktien is not None
        assert aktien.value == 90.0

    def test_bei_gleichem_einreichungsdatum_entscheidet_nicht_die_reihenfolge(self) -> None:
        """Sonst haengt das Ergebnis am JSON -- genau das, was die Regel
        ausschliessen soll. Heute ohne praktische Wirkung, ueber vier
        geprueften Emittenten gibt es keinen solchen Gleichstand."""
        def antwort(zuerst: str, dann: str) -> dict[str, Any]:
            return _antwort(
                {
                    "Revenues": _usd(
                        _fakt(
                            1.0, start="2024-01-01", end="2024-12-31",
                            accn=zuerst, filed="2025-02-01",
                        ),
                        _fakt(
                            2.0, start="2024-01-01", end="2024-12-31",
                            accn=dann, filed="2025-02-01",
                        ),
                    )
                }
            )

        eine = resolve_company_facts(antwort("a", "b")).figures[FigureName.REVENUE][0]
        andere = resolve_company_facts(antwort("b", "a")).figures[FigureName.REVENUE][0]
        assert eine.source.accession == andere.source.accession == "b"

    def test_ohne_dei_gibt_es_keine_aktienzahl(self) -> None:
        antwort = _antwort({"Revenues": _usd(_fakt(1.0, start="2024-01-01", end="2024-12-31"))})
        assert resolve_company_facts(antwort).shares_outstanding is None
