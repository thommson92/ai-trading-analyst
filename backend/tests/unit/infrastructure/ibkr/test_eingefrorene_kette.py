"""Gegenprobe an einer echten IBKR-Optionskette (A2-M7).

``test_option_chain.py`` prueft jede Regel an einer eigens gebauten Antwort.
Das ist die Grenze dieser Tests: Sie schreiben hin, was sie erwarten, und
koennen deshalb nicht bemerken, wenn die TWS etwas anderes liefert -- ein
umbenanntes Feld, ein fehlendes Greek, eine andere Handelsklasse.

Hier laeuft dieselbe Kette gegen die **aufgezeichneten Rohantworten** vom
2026-09-01. Gerechnet wird neu; eingefroren ist nur, was der Anbieter gab.
Herkunft und Neuaufzeichnung stehen in ``data/HERKUNFT.md``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from ai_trading_analyst.domain.analysis import ContractSpec, Stock
from ai_trading_analyst.domain.options import (
    LiquidityGrade,
    OptionQuote,
    OptionsParameters,
    OptionsStatus,
)
from ai_trading_analyst.infrastructure.ibkr import (
    IbkrOptionsProvider,
    OptionChainStructure,
)

AAPL = ContractSpec(symbol="AAPL", exchange="SMART", currency="USD", primary_exchange="NASDAQ")
AKTIE = Stock(id=uuid4(), symbol="AAPL", exchange="NASDAQ")
BEWERTET_AM = datetime(2026, 9, 1, 17, 2, 56, tzinfo=UTC)


def _aufzeichnung() -> dict[str, Any]:
    pfad = Path(__file__).parent / "data" / "optionskette-AAPL.json"
    inhalt: dict[str, Any] = json.loads(pfad.read_text(encoding="utf-8"))
    return inhalt


class WiedergabeQuelle:
    """Spielt die aufgezeichneten Antworten zurueck -- und nur sie.

    Fragt der Adapter etwas anderes ab als damals, ist das kein stiller
    Rueckfall auf einen Ersatzwert, sondern ein Fehlschlag: Die Aufzeichnung
    beantwortet genau eine Frage, und eine andere Frage macht sie wertlos.
    """

    def __init__(self, aufzeichnung: dict[str, Any]) -> None:
        self._daten = aufzeichnung
        self.abgefragte_strikes: tuple[float, ...] = ()

    def option_chain(self, contract: ContractSpec) -> OptionChainStructure:
        abschnitt = self._daten["option_chain"]
        return OptionChainStructure(
            expirations=tuple(date.fromisoformat(t) for t in abschnitt["expirations"]),
            trading_class=abschnitt["trading_class"],
            exchange=abschnitt["exchange"],
        )

    def option_strikes(
        self, contract: ContractSpec, expiration: date, trading_class: str
    ) -> tuple[float, ...]:
        abschnitt = self._daten["option_strikes"]
        assert expiration == date.fromisoformat(abschnitt["expiration"])
        assert trading_class == abschnitt["trading_class"]
        return tuple(abschnitt["strikes"])

    def option_quotes(
        self,
        contract: ContractSpec,
        expiration: date,
        strikes: Sequence[float],
        market_data_type: int,
        trading_class: str,
    ) -> Sequence[OptionQuote]:
        abschnitt = self._daten["option_quotes"]
        assert expiration == date.fromisoformat(abschnitt["expiration"])
        self.abgefragte_strikes = tuple(strikes)
        return tuple(
            OptionQuote(
                expiration=date.fromisoformat(eintrag["expiration"]),
                strike=eintrag["strike"],
                bid=eintrag["bid"],
                ask=eintrag["ask"],
                delta=eintrag["delta"],
                implied_volatility=eintrag["implied_volatility"],
                open_interest=eintrag["open_interest"],
                volume=eintrag["volume"],
            )
            for eintrag in abschnitt["quotes"]
        )


def _analyse(quelle: WiedergabeQuelle) -> Any:
    daten = _aufzeichnung()
    provider = IbkrOptionsProvider(
        quelle,
        watchlist=[AAPL],
        parameters=OptionsParameters(),
        market_data_type=daten["marktdatentyp"],
        now=lambda: BEWERTET_AM,
    )
    return provider.options(
        AKTIE, price=daten["kurs"], as_of=date.fromisoformat(daten["stichtag"])
    )


class TestDieAufzeichnungSelbst:
    def test_sie_traegt_alle_drei_abrufe(self) -> None:
        """Ohne den Notierungsteil waere sie als Contract-Test wertlos --
        dann haette der Lauf vor dem dritten Abruf geendet."""
        daten = _aufzeichnung()

        assert daten["dateiformat"] == 1
        assert {"option_chain", "option_strikes", "option_quotes"} <= set(daten)
        assert daten["option_quotes"]["quotes"]


class TestDieKetteAnEchtenAntworten:
    def test_die_wahl_faellt_auf_denselben_verfallstermin(self) -> None:
        """23 gelistete Termine, davon liegen mehrere im Laufzeitfenster.

        Gewaehlt wird nicht der fruehste zulaessige, sondern der der
        bevorzugten Laufzeit naechste (ADR 0048, Festlegung 4) -- an dieser
        echten Kette ist das der 2026-10-02 mit 32 Tagen und nicht der
        2026-09-25 mit 25. An einer selbst gebauten Terminliste laesst sich
        dieser Unterschied uebersehen.
        """
        analyse = _analyse(WiedergabeQuelle(_aufzeichnung()))

        assert analyse.status is OptionsStatus.COMPLETED
        assert analyse.expiration == date(2026, 10, 2)

    def test_das_strike_band_schneidet_aus_61_gelisteten_zwoelf_heraus(self) -> None:
        """Die Kette fuehrt zu diesem Termin 61 Strikes von 110 bis 415.

        Angefragt werden nur die im Moneyness-Band -- jede Notierung kostet
        eine Marktdatenanfrage. 49 nicht gestellte Anfragen je Titel sind der
        Unterschied zwischen einem Tageslauf und einem Nachmittag.
        """
        quelle = WiedergabeQuelle(_aufzeichnung())

        _analyse(quelle)

        assert len(_aufzeichnung()["option_strikes"]["strikes"]) == 61
        assert len(quelle.abgefragte_strikes) == 12
        assert max(quelle.abgefragte_strikes) == 310.0
        assert min(quelle.abgefragte_strikes) == 255.0

    def test_kein_angefragter_strike_liegt_ueber_dem_kurs(self) -> None:
        """Ein Put ueber dem Kurs waere im Geld -- er gehoert nicht in eine
        Cash-Secured-Put-Auswahl."""
        quelle = WiedergabeQuelle(_aufzeichnung())

        _analyse(quelle)

        assert all(strike < _aufzeichnung()["kurs"] for strike in quelle.abgefragte_strikes)

    def test_der_beste_vorschlag_rechnet_sich_wie_am_laufabend(self) -> None:
        """Die Zahlen aus der Ausgabe des Serverlaufs vom 2026-09-01.

        Sie stehen hier vollstaendig und nicht als Stichprobe: Praemie,
        Break-even und Kapital sind die Rohgroessen, aus denen sich die
        Rendite nachrechnen laesst -- und sie zusammen brechen, wenn eine
        einzige Formel sich verschiebt.
        """
        analyse = _analyse(WiedergabeQuelle(_aufzeichnung()))

        bester = analyse.strategies[0]
        assert bester.strike == 310.0
        assert bester.days_to_expiration == 32
        assert bester.bid == 3.35
        assert bester.ask == 3.60
        assert bester.premium == pytest.approx(3.475)
        assert bester.break_even == pytest.approx(306.525)
        assert bester.capital_at_risk == pytest.approx(31_000.0)
        assert bester.simple_return == pytest.approx(0.0112, abs=1e-4)
        assert bester.annualized_return == pytest.approx(0.1279, abs=1e-4)

    def test_das_delta_kommt_als_betrag_an(self) -> None:
        """Die TWS liefert es fuer einen Put negativ; gefiltert und
        ausgewiesen wird der Betrag."""
        analyse = _analyse(WiedergabeQuelle(_aufzeichnung()))

        roh = _aufzeichnung()["option_quotes"]["quotes"][0]["delta"]
        assert roh < 0
        bester = analyse.strategies[0]
        assert bester.delta == pytest.approx(0.2342, abs=1e-4)

    def test_die_vorschlaege_stehen_nach_rendite_absteigend(self) -> None:
        analyse = _analyse(WiedergabeQuelle(_aufzeichnung()))

        renditen = [vorschlag.annualized_return for vorschlag in analyse.strategies]
        assert renditen == sorted(renditen, reverse=True)

    def test_das_fehlende_open_interest_bleibt_fehlend(self) -> None:
        """**Der Befund, den nur eine echte Antwort liefert.** Im
        'frozen'-Marktdatenmodus gibt die TWS zu keinem der zwoelf Kontrakte
        ein Open Interest heraus -- bei durchweg dreistelligem Volumen.

        Eine 0 an dieser Stelle hiesse "niemand haelt diesen Kontrakt" und
        waere eine Aussage ueber den Markt, die niemand gemacht hat
        (CLAUDE.md). Die Liquiditaetsbewertung muss trotzdem zu einem Urteil
        kommen -- sie stuetzt sich hier auf Spanne und Volumen.
        """
        analyse = _analyse(WiedergabeQuelle(_aufzeichnung()))

        notierungen = _aufzeichnung()["option_quotes"]["quotes"]
        assert all(eintrag["open_interest"] is None for eintrag in notierungen)
        assert all(vorschlag.open_interest is None for vorschlag in analyse.strategies)
        assert analyse.strategies[0].volume == 266
        assert analyse.strategies[0].liquidity is LiquidityGrade.GOOD

    def test_ohne_zonen_und_ohne_berichtstermin_bleiben_die_felder_leer(self) -> None:
        """Beide Kopplungen sind nicht blockierend: Der Vorschlag entsteht
        vollstaendig, die abhaengigen Felder sind gekennzeichnet leer. ``None``
        beim Berichtstermin heisst "unbekannt", nicht "keiner"."""
        analyse = _analyse(WiedergabeQuelle(_aufzeichnung()))

        bester = analyse.strategies[0]
        assert bester.distance_to_support_pct is None
        assert bester.earnings_within_term is None
