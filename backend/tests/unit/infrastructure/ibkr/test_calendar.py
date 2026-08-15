"""Der Boersenkalender aus IBKRs Handelszeiten.

Das Parsen ist reine Textarbeit und damit ohne TWS pruefbar -- gerade die
Faelle, auf die es ankommt: Feiertag, verkuerzter Tag, Jahreswechsel.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from ai_trading_analyst.domain.analysis import ContractSpec, MarketDataProviderError
from ai_trading_analyst.domain.scheduling import TradingCalendarError
from ai_trading_analyst.infrastructure.ibkr.calendar import (
    IbkrTradingCalendar,
    LiquidHoursError,
    parse_liquid_hours,
)

NEW_YORK = ZoneInfo("America/New_York")
AAPL = ContractSpec(symbol="AAPL", primary_exchange="NASDAQ")

# Thanksgiving-Woche 2026: Donnerstag Feiertag, Freitag verkuerzt.
THANKSGIVING = (
    "20261125:0930-20261125:1600;20261126:CLOSED;"
    "20261127:0930-20261127:1300;20261130:0930-20261130:1600"
)


class TestHandelszeitenLesen:
    def test_ein_gewoehnlicher_tag(self) -> None:
        sitzungen = parse_liquid_hours(THANKSGIVING, "America/New_York")
        mittwoch = sitzungen[date(2026, 11, 25)]

        assert mittwoch is not None
        assert mittwoch.open == datetime(2026, 11, 25, 9, 30, tzinfo=NEW_YORK)
        assert mittwoch.close == datetime(2026, 11, 25, 16, 0, tzinfo=NEW_YORK)

    def test_ein_feiertag_ergibt_none(self) -> None:
        """``None`` und nicht "kein Eintrag": Der Unterschied entscheidet, ob
        der Dispatcher schweigt oder Alarm schlaegt."""
        sitzungen = parse_liquid_hours(THANKSGIVING, "America/New_York")

        assert date(2026, 11, 26) in sitzungen
        assert sitzungen[date(2026, 11, 26)] is None

    def test_ein_verkuerzter_tag_traegt_seinen_frueheren_schluss(self) -> None:
        sitzungen = parse_liquid_hours(THANKSGIVING, "America/New_York")
        freitag = sitzungen[date(2026, 11, 27)]

        assert freitag is not None
        assert freitag.close.time() == time(13, 0)

    def test_die_zeitzone_ist_die_der_boerse(self) -> None:
        sitzungen = parse_liquid_hours("20260105:0930-20260105:1600", "America/New_York")
        januar = sitzungen[date(2026, 1, 5)]

        assert januar is not None
        assert januar.open.utcoffset().total_seconds() == -5 * 3600  # type: ignore[union-attr]

    @pytest.mark.parametrize(
        "kaputt",
        [
            "",
            "20261126",
            "2026112:CLOSED",
            "20261125:0930",
            "20261125:99-20261125:1600",
        ],
    )
    def test_unlesbares_wird_abgewiesen(self, kaputt: str) -> None:
        """Lieber ein Fehler als ein stillschweigend leerer Kalender -- der
        saehe aus wie lauter Feiertage."""
        with pytest.raises(LiquidHoursError):
            parse_liquid_hours(kaputt, "America/New_York")


class FakeQuelle:
    def __init__(self, antwort: str | Exception) -> None:
        self._antwort = antwort
        self.aufrufe = 0

    def liquid_hours(self, contract: ContractSpec) -> tuple[str, str]:
        self.aufrufe += 1
        if isinstance(self._antwort, Exception):
            raise self._antwort
        return self._antwort, "America/New_York"


class TestKalender:
    def test_ein_handelstag_kommt_als_sitzung_zurueck(self) -> None:
        kalender = IbkrTradingCalendar(FakeQuelle(THANKSGIVING), AAPL)
        assert kalender.session_on(date(2026, 11, 25)) is not None

    def test_ein_feiertag_kommt_als_none_zurueck(self) -> None:
        kalender = IbkrTradingCalendar(FakeQuelle(THANKSGIVING), AAPL)
        assert kalender.session_on(date(2026, 11, 26)) is None

    def test_ein_tag_ausserhalb_des_fensters_ist_keine_auskunft(self) -> None:
        """IBKR liefert nur ein Fenster um heute. Ein Datum ausserhalb darf
        nicht als Feiertag durchgehen -- das waere eine erfundene Auskunft."""
        kalender = IbkrTradingCalendar(FakeQuelle(THANKSGIVING), AAPL)

        with pytest.raises(TradingCalendarError, match="keinen Eintrag"):
            kalender.session_on(date(2026, 12, 24))

    def test_eine_nicht_erreichbare_tws_ist_keine_auskunft(self) -> None:
        quelle = FakeQuelle(MarketDataProviderError("Keine Verbindung zur TWS"))
        kalender = IbkrTradingCalendar(quelle, AAPL)

        with pytest.raises(TradingCalendarError, match="Keine Verbindung"):
            kalender.session_on(date(2026, 11, 25))

    def test_unlesbare_handelszeiten_ebenfalls_nicht(self) -> None:
        kalender = IbkrTradingCalendar(FakeQuelle("voelliger unsinn"), AAPL)

        with pytest.raises(TradingCalendarError, match="nicht lesbar"):
            kalender.session_on(date(2026, 11, 25))

    def test_gefragt_wird_nur_einmal(self) -> None:
        """Der Dispatcher laeuft einmal -- eine zweite Anfrage waere reine
        Last auf einer Verbindung, die ohnehin knapp ist."""
        quelle = FakeQuelle(THANKSGIVING)
        kalender = IbkrTradingCalendar(quelle, AAPL)

        kalender.session_on(date(2026, 11, 25))
        kalender.session_on(date(2026, 11, 26))

        assert quelle.aufrufe == 1
