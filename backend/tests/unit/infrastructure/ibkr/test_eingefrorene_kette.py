"""Gegenprobe an einer echten IBKR-Optionskette (A2-M7).

``test_option_chain.py`` prueft jede Regel an einer eigens gebauten Antwort.
Das ist die Grenze dieser Tests: Sie schreiben hin, was sie erwarten, und
koennen deshalb nicht bemerken, wenn die TWS etwas anderes liefert -- ein
umbenanntes Feld, ein fehlendes Greek, eine andere Handelsklasse.

Hier laeuft dieselbe Kette gegen die **aufgezeichneten Antworten** vom
2026-09-01. Gerechnet wird neu; eingefroren ist nur, was zurueckkam.

**Wie weit das reicht, und wie weit nicht.** Der Mitschnitt haengt am
Protokoll ``OptionChainSource`` -- also **hinter** ``_als_quote``, das den
``ib_async``-Ticker in die Domaene uebersetzt. Eingefroren ist damit die
Kettenstruktur nach dieser Uebersetzung, nicht das Drahtformat der TWS. Was
diese Tests bemerken: eine Aenderung an Terminwahl, Strike-Band,
Delta-Filter oder Renditeformel gegen eine echte, nicht selbst erdachte
Kette. Was sie **nicht** bemerken: wenn IBKR ein Ticker-Feld umbenennt und
``_als_quote`` es still auf ``None`` abbildet. Bei Finnhub liegt die Grenze
guenstiger -- dort geht das rohe JSON durch den echten Parser.

Diese Luecke zu schliessen hiesse, den Mitschnitt eine Ebene tiefer zu
setzen und je Ticker die Rohfelder mitzuschreiben. Das braucht einen neuen
Serverlauf bei offenem Markt und steht als Folgeschritt an.

Herkunft und Neuaufzeichnung stehen in ``data/HERKUNFT.md``.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
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
from ai_trading_analyst.infrastructure.ibkr.bar_source import _als_quote
from ai_trading_analyst.infrastructure.ibkr.chain_recorder import NICHT_ENDLICH

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
        self.abfragen: list[tuple[float, ...]] = []

    @property
    def abgefragte_strikes(self) -> tuple[float, ...]:
        """Die Strikes der **ersten** Abfrage -- das Moneyness-Band.

        Seit ADR 0058 Festlegung 11 folgt eine zweite, gezielte Abfrage fuer
        den Absicherungs-Strike. Sie hier mitzuzaehlen verwaesserte die
        Aussage der Tests, die das Band pruefen; die zweite hat ihre eigenen.
        """
        return self.abfragen[0] if self.abfragen else ()

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
        self.abfragen.append(tuple(strikes))
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


def _analyse(
    quelle: WiedergabeQuelle, parameters: OptionsParameters | None = None
) -> Any:
    daten = _aufzeichnung()
    provider = IbkrOptionsProvider(
        quelle,
        watchlist=[AAPL],
        parameters=parameters or OptionsParameters(),
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

    def test_der_absicherungs_strike_liegt_meist_schon_im_band(self) -> None:
        """Ein gemessener Befund, der die Annahme aus ADR 0058 Festlegung 11
        korrigiert.

        Das Moneyness-Band reicht bis 80 Prozent des Kurses, die Zielbreite
        der Absicherung betraegt 6,5 Prozent -- an dieser echten Kette (Kurs
        313,48, Band 310 bis 255) faellt der gesuchte 290er mitten hinein.
        Das Kontingent ist also **nicht** ausgeschoepft, und der zweite Abruf
        ist ein Rueckfall, keine Regel.

        Ihn trotzdem zu stellen kostete eine Anfrage umsonst -- und die
        Notierung ein zweites Mal anzuhaengen erzeugte eine Dublette in
        ``option_quotes``, ueber die die Kalibrierung dann mittelte.
        """
        quelle = WiedergabeQuelle(_aufzeichnung())

        analyse = _analyse(quelle)

        assert len(quelle.abfragen) == 1
        assert analyse.spread is not None
        assert analyse.spread.hedge_strike < analyse.strategies[0].strike
        strikes = [q.strike for q in analyse.quotes]
        assert analyse.spread.hedge_strike in strikes
        assert len(strikes) == len(set(strikes))

    def test_liegt_er_ausserhalb_wird_er_gezielt_nachgefragt(self) -> None:
        """Der Rueckfall: Eine Zielbreite von 25 Prozent fuehrt aus dem Band
        heraus. Dann -- und nur dann -- kostet der Vergleich eine zweite
        Anfrage, und sie holt genau einen Kontrakt."""
        quelle = WiedergabeQuelle(_aufzeichnung())

        _analyse(quelle, OptionsParameters(hedge_width_pct=0.25))

        assert len(quelle.abfragen) == 2
        assert len(quelle.abfragen[1]) == 1
        assert quelle.abfragen[1][0] < min(quelle.abfragen[0])

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

    def test_ohne_open_interest_kommt_die_bewertung_trotzdem_zu_einem_urteil(self) -> None:
        """Zwoelf Kontrakte, kein einziges Open Interest -- und trotzdem
        ``GOOD``, getragen von Spanne und Volumen.

        **Was hier nicht behauptet wird:** dass die TWS das Feld
        zurueckgehalten haette. ``reqTickers`` fordert es gar nicht erst an
        (Kommentar in ``bar_source._als_quote``), und der Mitschnitt setzt
        eine Ebene darueber an -- aus dem ``null`` in der Datei laesst sich
        die Ursache nicht ablesen. Geprueft ist die Wirkung: Ein fehlender
        Wert kostet den Vorschlag nicht, und er wird auch nicht durch eine 0
        ersetzt. Eine 0 hiesse "niemand haelt diesen Kontrakt" -- eine
        Aussage ueber den Markt, die niemand gemacht hat (CLAUDE.md).
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


def _als_ticker(roh: dict[str, Any]) -> Any:
    """Baut aus dem Rohabschnitt wieder das, was ``ib_async`` geliefert hat.

    ``"nan"`` wird zurueck zu ``float('nan')`` -- die Aufzeichnung haelt es
    als Zeichenkette fest, weil JSON den Wert nicht kennt.
    """

    def zahl(wert: Any) -> Any:
        return math.nan if wert == NICHT_ENDLICH else wert

    greeks = roh["modelGreeks"]
    return SimpleNamespace(
        contract=SimpleNamespace(
            lastTradeDateOrContractMonth=roh["contract"]["lastTradeDateOrContractMonth"],
            strike=zahl(roh["contract"]["strike"]),
            tradingClass=roh["contract"]["tradingClass"],
            conId=roh["contract"]["conId"],
        ),
        bid=zahl(roh["bid"]),
        ask=zahl(roh["ask"]),
        volume=zahl(roh["volume"]),
        putOpenInterest=zahl(roh["putOpenInterest"]),
        modelGreeks=None
        if greeks is None
        else SimpleNamespace(delta=zahl(greeks["delta"]), impliedVol=zahl(greeks["impliedVol"])),
    )


class TestDieUebersetzungAmDrahtformat:
    """Die Ebene, die der Kette darueber fehlt (Review vom 2026-09-01).

    Hier laeuft ``_als_quote`` ueber die **unuebersetzten** Felder, wie die
    TWS sie stellte. Benennt IBKR eines um oder wechselt es von ``NaN`` auf
    ``-1``, bricht dieser Test -- und nur dieser kann das.
    """

    def _rohe(self) -> list[dict[str, Any]]:
        daten = _aufzeichnung()
        rohe = daten.get("rohe_notierungen")
        if not rohe:
            pytest.skip(
                "Die eingefrorene Kette stammt aus Dateiformat 1 und hat keinen "
                "Rohabschnitt. Neu aufzeichnen mit 'cli options --record' bei "
                "laufender TWS und offenem Markt (Doc 14, Zwischenschritt "
                "'Contract-Antworten einfrieren')."
            )
        eintraege: list[dict[str, Any]] = rohe
        return eintraege

    def test_die_uebersetzung_ergibt_die_aufgezeichneten_notierungen(self) -> None:
        """Roh und uebersetzt stehen beide in der Datei. Dass sie
        zusammenpassen, ist die Zusage von ``_als_quote`` -- und sie wird hier
        nachgerechnet statt geglaubt."""
        erwartet = _aufzeichnung()["option_quotes"]["quotes"]

        gerechnet = [_als_quote(_als_ticker(roh)) for roh in self._rohe()]

        assert len(gerechnet) == len(erwartet)
        for quote, soll in zip(gerechnet, erwartet, strict=True):
            assert quote.strike == soll["strike"]
            assert quote.bid == soll["bid"]
            assert quote.ask == soll["ask"]
            assert quote.delta == soll["delta"]
            assert quote.implied_volatility == soll["implied_volatility"]
            assert quote.open_interest == soll["open_interest"]
            assert quote.volume == soll["volume"]

    def test_ein_nicht_gestelltes_feld_kam_als_nan_und_nicht_als_null(self) -> None:
        """Der Punkt, an dem die Review meine Formulierung korrigiert hat:
        Ob das leere Open Interest von der TWS kam oder von der Uebersetzung,
        liess sich aus der alten Aufzeichnung nicht ablesen. Aus dieser
        schon."""
        rohe = self._rohe()

        assert all(roh["putOpenInterest"] == NICHT_ENDLICH for roh in rohe)
        assert all(_als_quote(_als_ticker(roh)).open_interest is None for roh in rohe)
