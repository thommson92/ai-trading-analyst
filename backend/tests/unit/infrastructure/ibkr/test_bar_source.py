"""Die Teile der Barquelle, die ohne laufende TWS pruefbar sind.

Der eigentliche Verbindungsaufbau ist im Spike live gegen die TWS des
Projektinhabers belegt (``spikes/ibkr-marketdata/REPORT.md``, Frage 1 und 3)
und wird hier nicht nachgestellt -- ein Testdoppel fuer ``ib_async`` wuerde
nur die eigene Annahme ueber die Bibliothek pruefen.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from ai_trading_analyst.domain.analysis import ContractSpec
from ai_trading_analyst.infrastructure.ibkr.bar_source import (
    SUPPORTED_BAR_MINUTES,
    IbAsyncBarSource,
    IbkrBarSourceError,
    IbkrConnectionSettings,
    duration_in_days,
    ibkr_bar_size,
    ibkr_duration,
)

UNBESETZTER_PORT = IbkrConnectionSettings(
    host="127.0.0.1", port=1, client_id=17, connect_timeout_seconds=1.0
)
AAPL = ContractSpec(symbol="AAPL", primary_exchange="NASDAQ")


class TestBarGroesse:
    def test_die_minute_steht_in_der_einzahl(self) -> None:
        assert ibkr_bar_size(1) == "1 min"

    @pytest.mark.parametrize("minutes", [3, 5, 15])
    def test_alles_darueber_in_der_mehrzahl(self, minutes: int) -> None:
        assert ibkr_bar_size(minutes) == f"{minutes} mins"

    def test_eine_nicht_unterstuetzte_groesse_faellt_sofort_auf(self) -> None:
        # 13 teilt 195 zwar ohne Rest, IBKR kennt diese Bar-Groesse aber nicht.
        with pytest.raises(ValueError, match="13-Minuten-Bars"):
            ibkr_bar_size(13)

    def test_jede_unterstuetzte_groesse_teilt_die_kerze_ohne_rest(self) -> None:
        assert all(195 % minutes == 0 for minutes in SUPPORTED_BAR_MINUTES)


class TestVerhaltenOhneErreichbareTws:
    """Der wichtigste Betriebsfall (ADR 0014, E2): Die TWS laeuft nicht.

    Beide Tests laufen gegen einen garantiert unbesetzten Port -- kein
    Netzwerkverkehr nach aussen, kein IBKR-Konto, keine laufende TWS.
    """

    def test_der_abruf_meldet_einen_klaren_verbindungsfehler(self) -> None:
        quelle = IbAsyncBarSource(UNBESETZTER_PORT, native_bar_minutes=15, duration="1 D")
        with pytest.raises(IbkrBarSourceError, match="Keine Verbindung zur TWS"):
            quelle.fetch_intraday_bars(AAPL)

    def test_auch_aus_einem_worker_thread_heraus(self) -> None:
        """FastAPI fuehrt synchrone Endpunkte in Worker-Threads aus.

        Ohne den vorbereiteten Event-Loop scheitert dort bereits der Aufbau
        des ib_async-Clients -- und zwar mit "There is no current event loop
        in thread" statt mit dem Hinweis auf die nicht gestartete TWS. Der
        produktive Weg waere damit unbenutzbar.
        """
        quelle = IbAsyncBarSource(UNBESETZTER_PORT, native_bar_minutes=15, duration="1 D")
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(quelle.fetch_intraday_bars, AAPL)
            with pytest.raises(IbkrBarSourceError, match="Keine Verbindung zur TWS"):
                future.result()

    def test_close_ist_auch_ohne_bestehende_verbindung_gefahrlos(self) -> None:
        quelle = IbAsyncBarSource(UNBESETZTER_PORT, native_bar_minutes=15, duration="1 D")
        quelle.close()
        quelle.close()


class TestPacing:
    """IBKR sperrt bei mehr als 60 Historienanfragen je zehn Minuten die
    gesamte Verbindung. Der Abstand wird deshalb selbst eingehalten."""

    @staticmethod
    def _quelle(interval: float, uhr: list[float], geschlafen: list[float]) -> IbAsyncBarSource:
        def sleep(seconds: float) -> None:
            geschlafen.append(seconds)
            uhr[0] += seconds

        return IbAsyncBarSource(
            UNBESETZTER_PORT,
            native_bar_minutes=15,
            duration="1 D",
            minimum_request_interval_seconds=interval,
            sleep=sleep,
            monotonic=lambda: uhr[0],
        )

    def test_die_erste_anfrage_wartet_nicht(self) -> None:
        uhr: list[float] = [100.0]
        geschlafen: list[float] = []
        quelle = self._quelle(11.0, uhr, geschlafen)
        quelle._wait_for_pacing()
        assert geschlafen == []

    def test_eine_unmittelbar_folgende_anfrage_wartet_den_vollen_abstand(self) -> None:
        uhr: list[float] = [100.0]
        geschlafen: list[float] = []
        quelle = self._quelle(11.0, uhr, geschlafen)
        quelle._wait_for_pacing()
        quelle._wait_for_pacing()
        assert geschlafen == [11.0]

    def test_eine_ohnehin_verstrichene_wartezeit_wird_nicht_nachgeholt(self) -> None:
        uhr: list[float] = [100.0]
        geschlafen: list[float] = []
        quelle = self._quelle(11.0, uhr, geschlafen)
        quelle._wait_for_pacing()
        uhr[0] += 30.0  # der Abruf selbst hat laenger gedauert als der Abstand
        quelle._wait_for_pacing()
        assert geschlafen == []

    def test_abstand_null_schaltet_die_bremse_ab(self) -> None:
        uhr: list[float] = [100.0]
        geschlafen: list[float] = []
        quelle = self._quelle(0.0, uhr, geschlafen)
        quelle._wait_for_pacing()
        quelle._wait_for_pacing()
        assert geschlafen == []


class TestZeitraumangabe:
    """Die Uebersetzung einer Tagesangabe in die Schreibweise der IBKR-API."""

    def test_tage_bleiben_tage(self) -> None:
        assert ibkr_duration(1) == "1 D"
        assert ibkr_duration(30) == "30 D"

    def test_bis_365_tage_sind_zulaessig(self) -> None:
        assert ibkr_duration(365) == "365 D"

    def test_darueber_wird_in_jahren_gerechnet(self) -> None:
        """Die API nimmt Tagesangaben nur bis 365 an."""
        assert ibkr_duration(366) == "2 Y"
        assert ibkr_duration(730) == "2 Y"
        assert ibkr_duration(731) == "3 Y"

    def test_aufgerundet_wird_bewusst(self) -> None:
        """Lieber ein paar Bars zu viel als eine Luecke -- doppelte werden
        beim Speichern ohnehin uebergangen."""
        assert ibkr_duration(400) == "2 Y"

    def test_null_tage_sind_kein_gueltiger_zeitraum(self) -> None:
        with pytest.raises(ValueError, match="mindestens 1"):
            ibkr_duration(0)


class TestZeitraumangabeInTage:
    """Die Gegenrichtung: Der Standardzeitraum steht in der Konfiguration in
    IBKR-Schreibweise, die Kuerzungspruefung des Backfills rechnet in Tagen."""

    def test_die_ausgelieferte_einstellung(self) -> None:
        assert duration_in_days("1 Y") == 365

    def test_alle_einheiten(self) -> None:
        assert duration_in_days("30 D") == 30
        assert duration_in_days("2 W") == 14
        assert duration_in_days("6 M") == 180

    def test_die_umkehrung_von_ibkr_duration(self) -> None:
        assert duration_in_days(ibkr_duration(30)) == 30
        assert duration_in_days(ibkr_duration(365)) == 365

    def test_eine_unbekannte_einheit_wird_abgelehnt(self) -> None:
        with pytest.raises(ValueError, match="keine IBKR-Zeitraumangabe"):
            duration_in_days("1 Jahr")

    def test_eine_angabe_ohne_einheit_wird_abgelehnt(self) -> None:
        with pytest.raises(ValueError, match="keine IBKR-Zeitraumangabe"):
            duration_in_days("365")

    def test_eine_angabe_ohne_zahl_wird_abgelehnt(self) -> None:
        with pytest.raises(ValueError, match="ganzen Zahl"):
            duration_in_days("ein Y")

    def test_null_ergibt_keinen_zeitraum(self) -> None:
        with pytest.raises(ValueError, match="keinen Zeitraum"):
            duration_in_days("0 D")
