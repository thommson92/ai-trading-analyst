"""Die Auswertung der Finnhub-Antwort.

Der Abruf selbst braucht einen Schluessel und ist nicht Gegenstand dieser
Tests. Geprueft wird, was fachlich zaehlt: dass die Sonde eine fehlende
Kennzeichnung bestaetigt/geschaetzt als **Befund** meldet statt sie zu
uebersehen, und dass der Schluessel nirgends durchrutscht.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe_finnhub import (
    API_KEY_VARIABLE,
    TREFFERGRENZE,
    ProbeError,
    fetch_in_chunks,
    read_api_key,
    summarize,
    watchlist_symbols,
)

OHNE_KENNZEICHNUNG = [
    {"date": "2026-08-20", "symbol": "AAPL", "hour": "amc", "quarter": 3, "year": 2026},
    {"date": "2026-08-21", "symbol": "WMT", "hour": "bmo", "quarter": 2, "year": 2026},
]

MIT_KENNZEICHNUNG = [
    {"date": "2026-08-20", "symbol": "AAPL", "hour": "amc", "dateConfirmed": True},
    {"date": "2026-08-21", "symbol": "WMT", "hour": "bmo", "dateConfirmed": False},
]


class TestKennzeichnung:
    def test_fehlende_kennzeichnung_wird_als_befund_gemeldet(self) -> None:
        """Der wichtigste Fall: Ohne Kennzeichnung darf die Sonde nicht
        schweigen, sonst wuerde ein geschaetzter Termin spaeter wie ein
        bestaetigter behandelt."""
        ausgabe = "\n".join(summarize(OHNE_KENNZEICHNUNG, []))
        assert "KEIN solches Feld vorhanden" in ausgabe

    def test_vorhandene_kennzeichnung_wird_mit_ihren_werten_gezeigt(self) -> None:
        ausgabe = "\n".join(summarize(MIT_KENNZEICHNUNG, []))
        assert "dateConfirmed" in ausgabe
        assert "False | True" in ausgabe


class TestZusammenfassung:
    def test_felder_werden_mit_fuellgrad_ausgewiesen(self) -> None:
        eintraege = [*OHNE_KENNZEICHNUNG, {"date": "2026-08-22", "symbol": "MSFT"}]
        ausgabe = "\n".join(summarize(eintraege, []))
        assert "symbol" in ausgabe
        assert "2 mit Wert" in ausgabe  # hour fehlt beim dritten Eintrag

    def test_ein_vorhandenes_feld_ohne_wert_zaehlt_nicht_als_gefuellt(self) -> None:
        """``epsActual: null`` ist bei kuenftigen Terminen der Normalfall --
        ein Fuellgrad von 100 Prozent waere hier eine Luege."""
        eintraege = [{"date": "2026-08-20", "symbol": "AAPL", "epsActual": None}]
        ausgabe = "\n".join(summarize(eintraege, []))
        assert "epsActual                1 vorhanden,     0 mit Wert" in ausgabe

    def test_mehrfach_genannte_symbole_werden_gemeldet(self) -> None:
        eintraege = [
            {"date": "2026-08-20", "symbol": "AAPL"},
            {"date": "2026-11-20", "symbol": "AAPL"},
        ]
        assert "AAPL" in "\n".join(summarize(eintraege, []))
        assert "erscheinen mehrfach" in "\n".join(summarize(eintraege, []))

    def test_die_tageszeit_wird_ausgewertet(self) -> None:
        """Ohne sie ist ein Termin fuer einen Filter auf 195-Minuten-Kerzen
        unscharf."""
        ausgabe = "\n".join(summarize(OHNE_KENNZEICHNUNG, []))
        assert "amc: 1" in ausgabe
        assert "bmo: 1" in ausgabe

    def test_abdeckung_zaehlt_nur_die_watchlist(self) -> None:
        ausgabe = "\n".join(summarize(OHNE_KENNZEICHNUNG, ["AAPL", "NVDA", "TSLA"]))
        assert "Watchlist: 3 Symbole" in ausgabe
        assert "davon im Zeitraum mit Termin: 1" in ausgabe

    def test_titel_ohne_termin_werden_namentlich_genannt(self) -> None:
        """Ueber vier Monate muss jeder Quartalsberichterstatter einmal
        auftauchen -- wer fehlt, ist der interessante Fall."""
        ausgabe = "\n".join(summarize(OHNE_KENNZEICHNUNG, ["AAPL", "NVDA", "TSLA"]))
        assert "OHNE Termin (2): NVDA, TSLA" in ausgabe

    def test_vollstaendige_abdeckung_wird_als_solche_gemeldet(self) -> None:
        assert "Kein Titel ohne Termin." in "\n".join(
            summarize(OHNE_KENNZEICHNUNG, ["AAPL", "WMT"])
        )

    def test_ohne_watchlist_entfaellt_der_abschnitt(self) -> None:
        assert "Abdeckung" not in "\n".join(summarize(OHNE_KENNZEICHNUNG, []))


class TestVorlaufanalyse:
    """Ob eine gefuellte Tageszeit ein bestaetigter Termin ist, entscheidet
    die Verteilung ueber den Vorlauf -- nicht eine Vermutung."""

    @staticmethod
    def _in_tagen(tage: int, hour: str) -> dict[str, str]:
        termin = date.today() + timedelta(days=tage)  # noqa: DTZ011
        return {"date": termin.isoformat(), "symbol": "X", "hour": hour}

    def test_der_vorlauf_wird_in_wochen_aufgeschluesselt(self) -> None:
        eintraege = [self._in_tagen(2, "amc"), self._in_tagen(30, "")]
        ausgabe = "\n".join(summarize(eintraege, []))
        assert "in  0 Woche(n):    1 von    1 mit Tageszeit (100 %)" in ausgabe
        assert "in  4 Woche(n):    0 von    1 mit Tageszeit (0 %)" in ausgabe

    def test_die_watchlist_wird_getrennt_ausgewiesen(self) -> None:
        """Der Unterschied entscheidet, ob die Tageszeit ein
        Bestaetigungssignal oder ein Groesseneffekt ist."""
        eintraege = [
            {"date": self._in_tagen(2, "amc")["date"], "symbol": "AAPL", "hour": "amc"},
            {"date": self._in_tagen(2, "")["date"], "symbol": "WINZIG", "hour": ""},
        ]
        ausgabe = "\n".join(summarize(eintraege, ["AAPL"]))
        assert "Nur die eigene Watchlist" in ausgabe
        assert "Watchlist: 100 %" in ausgabe
        assert "uebrige:   0 %" in ausgabe

    def test_ein_unlesbares_datum_bricht_die_auswertung_nicht_ab(self) -> None:
        eintraege = [{"date": "keine Angabe", "symbol": "X", "hour": "amc"}]
        assert summarize(eintraege, [])  # keine Ausnahme, Rest bleibt nutzbar


class TestFensterweiserAbruf:
    """Eine Anfrage ueber 120 Tage lieferte 1500 Eintraege -- und darin nur
    Termine der letzten sechs Wochen. Kurze Fenster umgehen das."""

    @staticmethod
    def _antworten(seiten: list[list[dict[str, str]]]) -> object:
        aufrufe: list[tuple[date, date]] = []

        def falscher_abruf(_key: str, von: date, bis: date) -> dict[str, object]:
            aufrufe.append((von, bis))
            return {"earningsCalendar": seiten[len(aufrufe) - 1]}

        falscher_abruf.aufrufe = aufrufe  # type: ignore[attr-defined]
        return falscher_abruf

    def test_der_zeitraum_wird_in_fenster_zerlegt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        abruf = self._antworten([[], [], []])
        monkeypatch.setattr("probe_finnhub.fetch_calendar", abruf)

        fetch_in_chunks("k", date(2026, 8, 13), date(2026, 10, 11), 30)

        assert abruf.aufrufe == [  # type: ignore[attr-defined]
            (date(2026, 8, 13), date(2026, 9, 11)),
            (date(2026, 9, 12), date(2026, 10, 11)),
        ]

    def test_dubletten_ueber_fenstergrenzen_hinweg_verschwinden(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gleicher = {"symbol": "AAPL", "date": "2026-09-11"}
        monkeypatch.setattr(
            "probe_finnhub.fetch_calendar", self._antworten([[gleicher], [gleicher]])
        )

        eintraege, _ = fetch_in_chunks("k", date(2026, 8, 13), date(2026, 10, 11), 30)

        assert len(eintraege) == 1

    def test_ein_gekuerztes_fenster_wird_geteilt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Genau so sah die Kuerzung aus: exakt 1500 Eintraege, ohne dass die
        Antwort es kenntlich gemacht haette. Eine feste Fenstergroesse
        genuegt nicht -- 30 Tage reichen im September und laufen Ende Oktober
        in die Grenze."""
        gekuerzt = [{"symbol": f"S{i}", "date": "2026-09-01"} for i in range(TREFFERGRENZE)]
        haelfte = [{"symbol": "A", "date": "2026-08-14"}]
        abruf = self._antworten([gekuerzt, haelfte, haelfte])
        monkeypatch.setattr("probe_finnhub.fetch_calendar", abruf)

        eintraege, hinweise = fetch_in_chunks("k", date(2026, 8, 13), date(2026, 8, 20), 30)

        assert len(abruf.aufrufe) == 3  # type: ignore[attr-defined]
        assert "wird geteilt" in hinweise[0]
        assert len(eintraege) == 1  # beide Haelften liefern denselben Eintrag

    def test_ein_einzelner_tag_wird_nicht_weiter_geteilt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sonst liefe die Teilung endlos. Ein Tag an der Grenze ist ein
        Befund, kein Fall fuer eine weitere Halbierung."""
        gekuerzt = [{"symbol": f"S{i}", "date": "2026-08-13"} for i in range(TREFFERGRENZE)]
        abruf = self._antworten([gekuerzt])
        monkeypatch.setattr("probe_finnhub.fetch_calendar", abruf)

        _, hinweise = fetch_in_chunks("k", date(2026, 8, 13), date(2026, 8, 13), 30)

        assert len(abruf.aufrufe) == 1  # type: ignore[attr-defined]
        assert "nicht weiter teilbar" in hinweise[0]


class TestWatchlist:
    def test_boersenpraefix_und_mehrfachnennungen_verschwinden(self, tmp_path: Path) -> None:
        (tmp_path / "eine.txt").write_text("NASDAQ:AAPL,NYSE:BRK.B,NASDAQ:AAPL", encoding="utf-8")
        assert watchlist_symbols(tmp_path) == ["AAPL", "BRK.B"]

    def test_abschnittsueberschriften_werden_uebergangen(self, tmp_path: Path) -> None:
        (tmp_path / "eine.txt").write_text("###GROSS,NASDAQ:AAPL", encoding="utf-8")
        assert watchlist_symbols(tmp_path) == ["AAPL"]


class TestSchluessel:
    def test_fehlender_schluessel_meldet_sich_verstaendlich(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(API_KEY_VARIABLE, raising=False)
        with pytest.raises(ProbeError, match=API_KEY_VARIABLE):
            read_api_key()

    def test_leerer_schluessel_gilt_als_fehlend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(API_KEY_VARIABLE, "   ")
        with pytest.raises(ProbeError):
            read_api_key()

    def test_der_schluessel_kommt_ausschliesslich_aus_der_umgebung(self) -> None:
        """Projektregel: Geheimnisse nur ueber ATA_-Variablen, nie als
        Argument -- ein Argument stuende in der Shell-Historie."""
        quelltext = (Path(__file__).resolve().parents[1] / "probe_finnhub.py").read_text(
            encoding="utf-8"
        )
        assert "--token" not in quelltext
        assert "--api-key" not in quelltext
        assert "os.environ.get(API_KEY_VARIABLE" in quelltext

    def test_der_schluessel_steht_in_keiner_ausgabe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(API_KEY_VARIABLE, "geheim-123")
        assert os.environ[API_KEY_VARIABLE] not in "\n".join(
            summarize(OHNE_KENNZEICHNUNG, ["AAPL"])
        )
