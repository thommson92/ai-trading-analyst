"""Wann dieses Programm die TWS in Ruhe laesst (ADR 0078).

Die Zeitpunkte pflegt der Inhaber. Diese Tests halten fest, was die
Konfiguration bedeutet -- damit eine geaenderte Zeile dort nicht
stillschweigend etwas anderes heisst als gedacht.
"""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from ai_trading_analyst.bootstrap import build_ruhezeiten
from ai_trading_analyst.config.loader import load_config
from ai_trading_analyst.config.settings import (
    RuhezeitenConfig,
    RuhezeitpunktConfig,
)
from ai_trading_analyst.infrastructure.ibkr import (
    ContractSpec,
    IbAsyncBarSource,
    IbkrBarSourceError,
    IbkrConnectionSettings,
)
from ai_trading_analyst.infrastructure.ibkr.ruhezeiten import Ruhezeiten, Ruhezeitpunkt

NEW_YORK = ZoneInfo("America/New_York")

WOCHENTAGS = frozenset({1, 2, 3, 4, 5})
NUR_FREITAG = frozenset({5})

#: Der vom Inhaber am 2026-10-09 validierte Stand.
VALIDIERT = Ruhezeiten(
    zeitpunkte=(
        Ruhezeitpunkt(zeit=time(13, 15), wochentage=WOCHENTAGS),
        Ruhezeitpunkt(zeit=time(14, 15), wochentage=WOCHENTAGS),
        Ruhezeitpunkt(zeit=time(14, 45), wochentage=NUR_FREITAG),
    ),
    radius=timedelta(minutes=5),
    zeitzone="America/New_York",
)

DONNERSTAG = datetime(2026, 10, 8, tzinfo=NEW_YORK)
FREITAG = datetime(2026, 10, 9, tzinfo=NEW_YORK)
SAMSTAG = datetime(2026, 10, 10, tzinfo=NEW_YORK)

VERBINDUNG = IbkrConnectionSettings(
    host="127.0.0.1", port=1, client_id=17, connect_timeout_seconds=1.0
)
"""Ein unbesetzter Port: Diese Tests pruefen die Wartestelle, und die liegt
vor dem Verbindungsaufbau."""

AAPL = ContractSpec(symbol="AAPL", primary_exchange="NASDAQ")


def _am(tag: datetime, stunde: int, minute: int) -> datetime:
    return tag.replace(hour=stunde, minute=minute)


class TestDerValidierteStand:
    """Was in ``config/default.yaml`` steht, in Tests gegossen."""

    def test_eine_minute_vor_dem_fenster_ist_frei(self) -> None:
        assert VALIDIERT.ende_der_sperre(_am(DONNERSTAG, 13, 9)) is None

    def test_der_beginn_gehoert_dazu(self) -> None:
        ende = VALIDIERT.ende_der_sperre(_am(DONNERSTAG, 13, 10))
        assert ende == _am(DONNERSTAG, 13, 20)

    def test_das_ende_gehoert_nicht_dazu(self) -> None:
        """Halboffen, damit zwei aneinandergrenzende Fenster keine Sekunde
        doppelt sperren -- und damit die Arbeit zur Minute wieder anlaeuft."""
        assert VALIDIERT.ende_der_sperre(_am(DONNERSTAG, 13, 20)) is None

    def test_das_zweite_taegliche_fenster_gilt_auch(self) -> None:
        ende = VALIDIERT.ende_der_sperre(_am(DONNERSTAG, 14, 14))
        assert ende == _am(DONNERSTAG, 14, 20)

    def test_der_freitagstermin_gilt_nur_freitags(self) -> None:
        assert VALIDIERT.ende_der_sperre(_am(DONNERSTAG, 14, 45)) is None
        assert VALIDIERT.ende_der_sperre(_am(FREITAG, 14, 45)) == _am(FREITAG, 14, 50)

    def test_am_wochenende_ist_nichts_gesperrt(self) -> None:
        assert VALIDIERT.ende_der_sperre(_am(SAMSTAG, 13, 15)) is None

    def test_vor_dem_handelsbeginn_ist_nichts_gesperrt(self) -> None:
        """Die einzige durchgehende Arbeitszeit des Backfills liegt zwischen
        12:50 und 13:10 -- dort darf kein Fenster liegen, sonst verlaengert
        sich der Lauf deutlich staerker als um zehn Minuten."""
        for minute in (50, 55, 59):
            assert VALIDIERT.ende_der_sperre(_am(DONNERSTAG, 12, minute)) is None
        assert VALIDIERT.ende_der_sperre(_am(DONNERSTAG, 13, 0)) is None

    def test_drei_fenster_an_einem_freitag_zwei_an_den_uebrigen(self) -> None:
        assert len(VALIDIERT.fenster_am(FREITAG.date())) == 3
        assert len(VALIDIERT.fenster_am(DONNERSTAG.date())) == 2
        assert VALIDIERT.fenster_am(SAMSTAG.date()) == ()


class TestAneinandergrenzendeFenster:
    """Zwei Zeitpunkte, deren Fenster sich beruehren, sind **eine** Sperre.

    Heute ueberlappt nichts. Die Zeitpunkte pflegt aber der Inhaber, und wer
    zwei enger legt, soll nicht in das zweite Fenster hineinlaufen, weil nur
    das erste abgewartet wurde.
    """

    ENG = Ruhezeiten(
        zeitpunkte=(
            Ruhezeitpunkt(zeit=time(13, 15), wochentage=WOCHENTAGS),
            Ruhezeitpunkt(zeit=time(13, 25), wochentage=WOCHENTAGS),
            Ruhezeitpunkt(zeit=time(13, 35), wochentage=WOCHENTAGS),
        ),
        radius=timedelta(minutes=5),
        zeitzone="America/New_York",
    )

    def test_drei_beruehrende_fenster_ergeben_eine_sperre(self) -> None:
        ende = self.ENG.ende_der_sperre(_am(DONNERSTAG, 13, 10))
        assert ende == _am(DONNERSTAG, 13, 40)

    def test_auch_aus_der_mitte_heraus(self) -> None:
        ende = self.ENG.ende_der_sperre(_am(DONNERSTAG, 13, 28))
        assert ende == _am(DONNERSTAG, 13, 40)


class TestAbgeschaltet:
    def test_ohne_zeitpunkte_ist_nichts_gesperrt(self) -> None:
        leer = Ruhezeiten(zeitpunkte=(), radius=timedelta(minutes=5), zeitzone="UTC")
        assert not leer.aktiv
        assert leer.ende_der_sperre(_am(DONNERSTAG, 13, 15)) is None

    def test_radius_null_schaltet_ab(self) -> None:
        """Der Weg zurueck, ohne die Zeitpunkte zu loeschen."""
        ohne = Ruhezeiten(
            zeitpunkte=(Ruhezeitpunkt(zeit=time(13, 15), wochentage=WOCHENTAGS),),
            radius=timedelta(),
            zeitzone="America/New_York",
        )
        assert not ohne.aktiv
        assert ohne.ende_der_sperre(_am(DONNERSTAG, 13, 15)) is None


class TestZeitzone:
    """Die Zeitpunkte stehen in Boersenzeit, nicht in Serverzeit.

    Die Sommerzeit der beiden Kontinente faellt an verschiedenen Tagen; eine
    in UTC gerechnete Sperre waere in diesen Wochen um eine Stunde daneben.
    """

    def test_dieselbe_boersenzeit_vor_und_nach_der_umstellung(self) -> None:
        # Die USA stellen am 2026-11-01 zurueck.
        vorher = datetime(2026, 10, 29, 13, 15, tzinfo=NEW_YORK)
        nachher = datetime(2026, 11, 5, 13, 15, tzinfo=NEW_YORK)
        assert VALIDIERT.ende_der_sperre(vorher) is not None
        assert VALIDIERT.ende_der_sperre(nachher) is not None

    def test_die_pruefung_rechnet_einen_utc_zeitstempel_um(self) -> None:
        """So kommt er aus dem Programm: Alles rechnet in UTC, nur die
        Zeitpunkte stehen in Boersenzeit."""
        in_utc = datetime(2026, 10, 8, 17, 15, tzinfo=UTC)  # 13:15 New York
        assert VALIDIERT.ende_der_sperre(in_utc) is not None


class _Uhr:
    """Eine Uhr, die nur durch ``sleep`` weiterlaeuft.

    So ist die Wartezeit pruefbar, ohne sie zu verbringen -- zehn Minuten
    echter Schlaf waeren in einem Testlauf nicht hinnehmbar.
    """

    def __init__(self, start: datetime) -> None:
        self.jetzt = start
        self.geschlafen: list[float] = []

    def now(self) -> datetime:
        return self.jetzt

    def sleep(self, sekunden: float) -> None:
        self.geschlafen.append(sekunden)
        self.jetzt += timedelta(seconds=sekunden)


class TestDieVerbindungWartet:
    """Die Sperre wirkt im einzigen Durchgang zu IBKR.

    Nicht in der Drossel: Die sitzt ausschliesslich vor
    ``reqHistoricalData``, und die Optionsabrufe gehen daran vorbei --
    ausgerechnet ``reqTickers`` belegt die Marktdatenleitungen, also die
    Ressource, die wir uns mit der zweiten Anwendung teilen.
    """

    def _quelle(self, uhr: _Uhr) -> IbAsyncBarSource:
        return IbAsyncBarSource(
            VERBINDUNG,
            native_bar_minutes=15,
            duration="1 D",
            sleep=uhr.sleep,
            now=uhr.now,
            ruhezeiten=VALIDIERT,
        )

    def test_im_fenster_wird_bis_zu_dessen_ende_gewartet(self) -> None:
        uhr = _Uhr(_am(DONNERSTAG, 13, 12))
        quelle = self._quelle(uhr)

        quelle._warte_auf_freies_fenster()

        assert uhr.jetzt == _am(DONNERSTAG, 13, 20)
        assert quelle.ruhesekunden == 8 * 60

    def test_in_kurzen_schritten_und_nicht_in_einem_stueck(self) -> None:
        """Ein ``sleep`` ueber acht Minuten liesse sich nicht unterbrechen."""
        uhr = _Uhr(_am(DONNERSTAG, 13, 12))

        self._quelle(uhr)._warte_auf_freies_fenster()

        assert max(uhr.geschlafen) <= 5.0
        assert len(uhr.geschlafen) > 1

    def test_ausserhalb_wird_nicht_gewartet(self) -> None:
        uhr = _Uhr(_am(DONNERSTAG, 13, 20))
        quelle = self._quelle(uhr)

        quelle._warte_auf_freies_fenster()

        assert uhr.geschlafen == []
        assert quelle.ruhesekunden == 0.0

    def test_ohne_ruhezeiten_wird_nie_gewartet(self) -> None:
        """Der ausgelieferte Zustand und der Weg zurueck."""
        uhr = _Uhr(_am(DONNERSTAG, 13, 12))
        quelle = IbAsyncBarSource(
            VERBINDUNG,
            native_bar_minutes=15,
            duration="1 D",
            sleep=uhr.sleep,
            now=uhr.now,
        )

        quelle._warte_auf_freies_fenster()

        assert uhr.geschlafen == []

    def test_die_ruhezeit_wird_getrennt_von_der_drossel_gezaehlt(self) -> None:
        """Wer die beiden zusammenzaehlte, koennte hinterher nicht sagen,
        welche der zwei Ursachen einen Lauf verlaengert hat."""
        uhr = _Uhr(_am(DONNERSTAG, 13, 12))
        quelle = self._quelle(uhr)

        quelle._warte_auf_freies_fenster()

        assert quelle.ruhesekunden > 0
        assert quelle.verschlafene_sekunden == 0.0

    def test_die_wartestelle_liegt_wirklich_im_weg(self) -> None:
        """**Der Test, der den Einbau prueft und nicht die Rechnung.**

        Die Methode direkt zu rufen beweist nur, dass sie funktioniert --
        nicht, dass irgendetwas sie ruft. Hier geht der Weg durch
        ``fetch_intraday_bars`` und damit durch ``_connection``: Der
        Verbindungsaufbau scheitert erwartungsgemaess am unbesetzten Port,
        aber die Uhr ist vorher um die Dauer des Fensters weitergelaufen.
        """
        uhr = _Uhr(_am(DONNERSTAG, 13, 12))
        quelle = self._quelle(uhr)

        with pytest.raises(IbkrBarSourceError):
            quelle.fetch_intraday_bars(AAPL)

        assert uhr.jetzt >= _am(DONNERSTAG, 13, 20)
        assert quelle.ruhesekunden == 8 * 60

    @pytest.mark.parametrize(
        ("weg", "argumente"),
        [
            ("fetch_intraday_bars", (AAPL,)),
            ("option_chain", (AAPL,)),
            ("option_strikes", (AAPL, date(2026, 11, 20), "AAPL")),
            ("liquid_hours", (AAPL,)),
        ],
    )
    def test_auch_die_optionswege_warten(self, weg: str, argumente: tuple[object, ...]) -> None:
        """**Nicht nur der Kerzenabruf.** ``reqTickers`` und die
        Kettenabfragen belegen die Marktdatenleitungen des Kontos -- also
        genau die Ressource, um die es in ADR 0078 geht. Sie gehen an der
        Drossel vorbei, aber nicht an ``_connection``.
        """
        uhr = _Uhr(_am(DONNERSTAG, 13, 12))
        quelle = self._quelle(uhr)

        with pytest.raises(Exception):  # noqa: B017 -- der Port ist unbesetzt
            getattr(quelle, weg)(*argumente)

        assert uhr.jetzt >= _am(DONNERSTAG, 13, 20)
        assert quelle.ruhesekunden == 8 * 60

    def test_ein_abbruchsignal_beendet_die_wartezeit_vorzeitig(self) -> None:
        """**Sonst kostet die Ruhezeit den Wiederholversuch, den ADR 0069
        kauft.** Ohne dieses Signal liefe der Backfill-Thread nach einem frueh
        abgebrochenen Lauf das Fenster zu Ende, waehrend der Hauptthread die
        Dispatcher-Sperre haelt -- und der naechste Start in fuenfzehn Minuten
        endete mit "in Arbeit".
        """
        uhr = _Uhr(_am(DONNERSTAG, 13, 12))
        quelle = self._quelle(uhr)
        abbruch = threading.Event()
        abbruch.set()

        with quelle.abbruchsignal(abbruch.is_set):
            quelle._warte_auf_freies_fenster()

        assert uhr.geschlafen == []
        assert uhr.jetzt == _am(DONNERSTAG, 13, 12)

    def test_das_signal_gilt_nur_im_block(self) -> None:
        """Ein dauerhaft hinterlegtes Signal eines beendeten Laufs waere beim
        naechsten schlimmer als keines."""
        uhr = _Uhr(_am(DONNERSTAG, 13, 12))
        quelle = self._quelle(uhr)

        with quelle.abbruchsignal(lambda: True):
            pass
        quelle._warte_auf_freies_fenster()

        assert uhr.jetzt == _am(DONNERSTAG, 13, 20)


class TestDieKonfigurationWeistTippfehlerAb:
    """**Die Stelle mit dem hoechsten Fehlerrisiko** (ADR 0078, Festlegung 1).

    Diese Datei pflegt der Inhaber von Hand. Ein Tippfehler darf nicht still
    zu einer taeglichen Sperre werden -- er muss den Start abbrechen, und zwar
    mit einer Meldung, die den Schluessel nennt.
    """

    def test_der_validierte_stand_laedt(self) -> None:
        punkte = (
            RuhezeitpunktConfig(zeit="13:15", wochentage=("Mo", "Di", "Mi", "Do", "Fr")),
            RuhezeitpunktConfig(zeit="14:45", wochentage=("Fr",)),
        )
        assert punkte[0].als_zeit() == time(13, 15)
        assert punkte[0].als_isotage() == WOCHENTAGS
        assert punkte[1].als_isotage() == NUR_FREITAG

    @pytest.mark.parametrize("falsch", ["13.15", "1315", "13:15:00", "25:00", ""])
    def test_eine_unguelige_uhrzeit_bricht_ab(self, falsch: str) -> None:
        with pytest.raises(ValidationError):
            RuhezeitpunktConfig(zeit=falsch, wochentage=("Fr",))

    def test_ein_unbekannter_wochentag_bricht_ab(self) -> None:
        """``Freitag`` statt ``Fr`` ist der naheliegende Fehler."""
        with pytest.raises(ValidationError):
            RuhezeitpunktConfig(zeit="13:15", wochentage=("Freitag",))

    def test_eine_leere_tagesliste_bricht_ab(self) -> None:
        """Entweder ein Tippfehler oder ein Zeitpunkt, der nichts tut --
        beides soll beim Laden auffallen und nicht im Betrieb."""
        with pytest.raises(ValidationError, match="mindestens einen Tag"):
            RuhezeitpunktConfig(zeit="13:15", wochentage=())

    def test_ein_vertippter_schluessel_bricht_ab(self) -> None:
        """``extra='forbid'``: ``wochentag`` statt ``wochentage`` waere sonst
        ein Zeitpunkt ohne Tage, der nie greift."""
        with pytest.raises(ValidationError):
            RuhezeitpunktConfig(zeit="13:15", wochentag=("Fr",))  # type: ignore[call-arg]

    @pytest.mark.parametrize("radius", [-1, 31, 50])
    def test_ein_unsinniger_radius_bricht_ab(self, radius: int) -> None:
        """**Der teuerste Tippfehler.** ``50`` statt ``5`` liesse die drei
        Fenster zu einer Sperre von 11:35 bis 16:25 verschmelzen: Der Lauf
        begaenne mitten darin, screente nie und meldete sich jeden Abend als
        ueberfaellig."""
        with pytest.raises(ValidationError):
            RuhezeitenConfig(radius_minuten=radius)

    def test_dreissig_minuten_sind_noch_erlaubt(self) -> None:
        assert RuhezeitenConfig(radius_minuten=30).radius_minuten == 30


class TestDieAusgelieferteKonfiguration:
    """Was in ``config/default.yaml`` steht, muss das sein, was wir meinen.

    Ohne diesen Test liesse eine geaenderte Zeile dort alle anderen Tests
    gruen -- sie bauen ihre Zeitpunkte von Hand nach.
    """

    def test_die_datei_ergibt_genau_den_validierten_stand(self) -> None:
        gebaut = build_ruhezeiten(load_config().config)

        assert gebaut is not None
        assert gebaut.radius == VALIDIERT.radius
        assert gebaut.zeitzone == VALIDIERT.zeitzone
        assert set(gebaut.zeitpunkte) == set(VALIDIERT.zeitpunkte)

    def test_die_fenster_liegen_hinter_der_durchgehenden_arbeitszeit(self) -> None:
        """Zwischen 12:50 und 13:10 liegt die einzige Zeit, in der der
        Backfill ununterbrochen arbeitet. Ein Fenster dort verlaengerte den
        Lauf deutlich staerker als zehn Minuten (ADR 0078, Folgen)."""
        gebaut = build_ruhezeiten(load_config().config)
        assert gebaut is not None

        for minute in range(50, 60):
            assert gebaut.ende_der_sperre(_am(DONNERSTAG, 12, minute)) is None
        for minute in range(0, 10):
            assert gebaut.ende_der_sperre(_am(DONNERSTAG, 13, minute)) is None


class TestDerWegZurueck:
    def _config(self, **felder: object) -> object:
        basis = load_config().config
        ibkr = basis.market_data.ibkr.model_copy(
            update={"ruhezeiten": RuhezeitenConfig(**felder)}
        )
        return basis.model_copy(
            update={"market_data": basis.market_data.model_copy(update={"ibkr": ibkr})}
        )

    def test_ohne_zeitpunkte_entsteht_keine_sperre(self) -> None:
        assert build_ruhezeiten(self._config(zeitpunkte=())) is None  # type: ignore[arg-type]

    def test_radius_null_entsteht_keine_sperre(self) -> None:
        """Der Weg zurueck ohne Deployment: Die Zeitpunkte bleiben stehen."""
        gebaut = build_ruhezeiten(
            self._config(  # type: ignore[arg-type]
                radius_minuten=0,
                zeitpunkte=(RuhezeitpunktConfig(zeit="13:15", wochentage=("Fr",)),),
            )
        )
        assert gebaut is None
