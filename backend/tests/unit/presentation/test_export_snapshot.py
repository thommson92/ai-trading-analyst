"""Der Datenbaum des externen Dashboards (ADR 0060, Spike-Bericht 8.2).

Zwei Zusagen stehen hier im Mittelpunkt. Erstens: Der Baum enthaelt **die
Antworten der Endpunkte** und keine zweite Rechnung -- er entsteht aus
denselben Funktionen wie die API. Zweitens: Er ist **deterministisch**;
derselbe Bestand ergibt dieselben Bytes, sonst waere "nur Neues hochladen"
nicht zu haben.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import cast

import pytest

from ai_trading_analyst.domain.analysis import (
    AnalysisRun,
    MarketDataProvider,
    MarketDataUnavailableError,
    RunStatus,
    UnitOfWork,
)
from ai_trading_analyst.domain.backtesting import BacktestParameters
from ai_trading_analyst.domain.scheduling import DashboardPublisherError
from ai_trading_analyst.domain.screening import CandidateRuleParameters
from ai_trading_analyst.infrastructure.publishing import (
    FORMAT_VERSION,
)
from ai_trading_analyst.infrastructure.publishing import (
    MANIFEST_PFAD as MANIFEST_PFAD_INFRA,
)
from ai_trading_analyst.presentation.export import (
    EXPORT_FASSUNG,
    MANIFEST_PFAD,
    SNAPSHOT_FORMAT,
    BekannteDatei,
    Exportdatei,
    Exportquellen,
    dateisicherer_name,
    iter_snapshot,
)
from ai_trading_analyst.presentation.export.snapshot import _export_fassung
from tests.unit.application.conftest import (
    FakeAnalysisRunRepository,
    FakeBacktestResultRepository,
    FakeMarketDataProvider,
    FakeOptionsBacktestResultRepository,
    FakeProcessingErrorRepository,
    FakeScreeningResultRepository,
    FakeStockReportRepository,
    FakeStockRepository,
    FakeUnitOfWork,
    InMemoryIntradayBarRepository,
    make_series,
    make_stock,
)

RULE = CandidateRuleParameters(
    required_crossing_signals=2, signal_lookback_previous_candles=5, warmup_candles=250
)
BACKTEST_PARAMS = BacktestParameters(
    horizons=(5, 10, 20),
    minimum_sample_size=10,
    normal_confidence_sample_size=30,
    history_years=5,
)


class _BestandNichtLesbar:
    """Ein Anbieter, dem die Quelle wegbricht -- nicht eine Aktie fehlt.

    ``MarketDataUnavailableError`` ist **Unterklasse** von
    ``MarketDataProviderError``. Genau deshalb muss der Test hier ansetzen und
    nicht an der Fabrik: Eine Fabrik, die wirft, prueft nur, dass ein
    ungefangener Fehler ungefangen bleibt.
    """

    def list_stocks(self) -> tuple[object, ...]:  # pragma: no cover -- nicht gebraucht
        return ()

    def get_candle_series(self, stock: object) -> object:
        raise MarketDataUnavailableError("Der Kursbestand ist gerade nicht lesbar.")


def quellen_mit(
    symbole: tuple[str, ...] = ("AAPL", "MSFT"),
    *,
    laeufe: tuple[AnalysisRun, ...] = (),
    ohne_chart: frozenset[str] = frozenset(),
    bestand_nicht_lesbar: bool = False,
) -> tuple[Exportquellen, FakeUnitOfWork]:
    stocks = FakeStockRepository()
    aktien = tuple(make_stock(symbol) for symbol in symbole)
    for aktie in aktien:
        stocks.add(aktie)

    runs = FakeAnalysisRunRepository()
    for lauf in laeufe:
        runs.add(lauf)

    uow = FakeUnitOfWork(
        stocks=stocks,
        intraday_bars=InMemoryIntradayBarRepository(),
        analysis_runs=runs,
        screening_results=FakeScreeningResultRepository(),
        processing_errors=FakeProcessingErrorRepository(),
        backtest_results=FakeBacktestResultRepository(),
        options_backtest_results=FakeOptionsBacktestResultRepository(),
        stock_reports=FakeStockReportRepository(),
    )

    reihen = {aktie.symbol: make_series(300, candidate=False) for aktie in aktien}

    def marktdaten() -> MarketDataProvider:
        if bestand_nicht_lesbar:
            return cast(MarketDataProvider, _BestandNichtLesbar())
        return FakeMarketDataProvider(aktien, reihen, error_symbols=ohne_chart)

    def uow_factory() -> UnitOfWork:
        return uow

    return (
        Exportquellen(
            uow_factory=uow_factory,
            backtest_parameters=BACKTEST_PARAMS,
            candidate_rule_parameters=RULE,
            chart_market_data=marktdaten,
        ),
        uow,
    )


def baum(quellen: Exportquellen, **kwargs: object) -> dict[str, bytes]:
    """Nur die tatsaechlich gebauten Dateien.

    Ein Eintrag ohne Inhalt heisst "unveraendert" (ADR 0068) -- er gehoert
    zum Baum, hat aber keine Bytes. Wer ihn sehen will, nimmt ``eintraege``.
    """
    return {
        datei.pfad: datei.inhalt
        for datei in iter_snapshot(quellen, **kwargs)  # type: ignore[arg-type]
        if datei.inhalt is not None
    }


def eintraege(quellen: Exportquellen, **kwargs: object) -> list[Exportdatei]:
    return list(iter_snapshot(quellen, **kwargs))  # type: ignore[arg-type]


def lauf(status: RunStatus = RunStatus.COMPLETED) -> AnalysisRun:
    return AnalysisRun(
        id=uuid.uuid4(),
        status=status,
        started_at=datetime(2026, 9, 5, 16, 45, tzinfo=UTC),
        completed_at=datetime(2026, 9, 5, 17, 20, tzinfo=UTC),
        number_of_stocks=2,
        candidates_found=0,
    )


class TestAufbau:
    def test_jede_aktie_bekommt_ihre_drei_dateien(self) -> None:
        quellen, _ = quellen_mit()
        dateien = baum(quellen)
        for symbol in ("AAPL", "MSFT"):
            assert f"data/stocks/{symbol}/reports.json" in dateien
            assert f"data/stocks/{symbol}/backtest.json" in dateien
            assert f"data/stocks/{symbol}/chart.json" in dateien

    def test_die_listen_liegen_an_der_wurzel(self) -> None:
        quellen, _ = quellen_mit()
        dateien = baum(quellen)
        assert "data/analysis-runs.json" in dateien
        assert "data/options-backtests.json" in dateien

    def test_jeder_lauf_bekommt_detail_und_berichtsliste(self) -> None:
        ein_lauf = lauf()
        quellen, _ = quellen_mit(laeufe=(ein_lauf,))
        dateien = baum(quellen)
        assert f"data/analysis-runs/{ein_lauf.id}.json" in dateien
        assert f"data/analysis-runs/{ein_lauf.id}/reports.json" in dateien

    def test_jede_datei_ist_gueltiges_json(self) -> None:
        quellen, _ = quellen_mit(laeufe=(lauf(),))
        dateien = baum(quellen)
        assert dateien, "Der Snapshot war leer -- dann prueft die Schleife nichts."
        for pfad, inhalt in dateien.items():
            assert json.loads(inhalt.decode("utf-8")) is not None, pfad


class TestManifest:
    def test_das_manifest_kommt_zuletzt(self) -> None:
        """Ein abgebrochener Export hinterlaesst damit keinen Stand -- statt
        einen unvollstaendigen zu behaupten."""
        quellen, _ = quellen_mit()
        pfade = [datei.pfad for datei in iter_snapshot(quellen)]
        assert pfade[-1] == MANIFEST_PFAD

    def test_das_manifest_nennt_den_stand(self) -> None:
        """Pflichtanzeige der Oberflaeche: Ein alter Stand muss alt aussehen."""
        ein_lauf = lauf()
        quellen, _ = quellen_mit(laeufe=(ein_lauf,))
        kennung = uuid.uuid4()
        zeit = datetime(2026, 9, 7, 21, 0, tzinfo=UTC)
        manifest = json.loads(
            baum(quellen, export_id=kennung, jetzt=zeit)[MANIFEST_PFAD].decode("utf-8")
        )
        assert manifest["format"] == SNAPSHOT_FORMAT
        assert manifest["export_id"] == str(kennung)
        assert manifest["exported_at"] == zeit.isoformat()
        assert manifest["run_id"] == str(ein_lauf.id)
        assert manifest["run_status"] == "COMPLETED"
        assert manifest["counts"]["stocks"] == 2

    def test_ohne_lauf_steht_kein_lauf_im_manifest(self) -> None:
        """Ein frischer Server hat noch keinen -- und behauptet keinen."""
        quellen, _ = quellen_mit()
        manifest = json.loads(baum(quellen)[MANIFEST_PFAD].decode("utf-8"))
        assert manifest["run_id"] is None
        assert manifest["counts"]["runs"] == 0

    def test_das_manifest_traegt_die_versionen(self) -> None:
        quellen, _ = quellen_mit()
        manifest = json.loads(baum(quellen)[MANIFEST_PFAD].decode("utf-8"))
        assert manifest["report_schema_version"]
        assert manifest["signal_rule_version"]
        assert manifest["application_version"]


class TestSymbolnamen:
    @pytest.mark.parametrize(
        ("symbol", "erwartet"),
        [("AAPL", "AAPL"), ("BRK B", "BRK-B"), ("BF.B", "BF-B"), ("aapl", "AAPL")],
    )
    def test_dateisichere_namen(self, symbol: str, erwartet: str) -> None:
        assert dateisicherer_name(symbol) == erwartet

    def test_zwei_symbole_mit_gleichem_namen_kollidieren_nicht(self) -> None:
        """``BRK B`` und ``BRK-B`` ergaeben denselben Verzeichnisnamen."""
        quellen, _ = quellen_mit(("BRK B", "BRK-B"))
        dateien = baum(quellen)
        namen = json.loads(dateien[MANIFEST_PFAD].decode("utf-8"))["symbols"]

        assert set(namen) == {"BRK B", "BRK-B"}
        assert len(set(namen.values())) == 2, "Zwei Aktien im selben Verzeichnis"
        for name in namen.values():
            assert f"data/stocks/{name}/chart.json" in dateien

    def test_die_zuordnung_steht_im_manifest(self) -> None:
        """Sonst muesste die Oberflaeche dieselbe Regel ein zweites Mal
        umsetzen -- und eine Abweichung faende niemand."""
        quellen, _ = quellen_mit(("BRK B",))
        manifest = json.loads(baum(quellen)[MANIFEST_PFAD].decode("utf-8"))
        assert manifest["symbols"] == {"BRK B": "BRK-B"}


class TestFehlendeCharts:
    def test_eine_aktie_ohne_kerzen_kostet_ihren_chart_nicht_den_export(self) -> None:
        quellen, _ = quellen_mit(ohne_chart=frozenset({"MSFT"}))
        dateien = baum(quellen)
        assert "data/stocks/AAPL/chart.json" in dateien
        assert "data/stocks/MSFT/chart.json" not in dateien
        # Die uebrigen Dateien der Aktie bleiben -- sie ist bekannt, nur ohne
        # Kursreihe.
        assert "data/stocks/MSFT/backtest.json" in dateien

    def test_fehlende_charts_stehen_im_manifest(self) -> None:
        """Ohne die Liste saehe eine Aktie ohne Kursreihe im Bestand aus wie
        eine, deren Datei beim Hochladen verloren ging."""
        quellen, _ = quellen_mit(ohne_chart=frozenset({"MSFT"}))
        manifest = json.loads(baum(quellen)[MANIFEST_PFAD].decode("utf-8"))
        assert manifest["stocks_without_chart"] == ["MSFT"]
        assert manifest["counts"]["charts"] == 1

    def test_keine_einzige_aktie_mit_chart_bricht_den_export_ab(self) -> None:
        """Der dritte Weg zu einem Baum ohne Charts -- und der leiseste.

        Nicht die Datenbank bricht ab, und nicht eine Aktie verliert ihre
        Reihe: **jede** verliert sie, jede einzeln und jede mit einer
        Meldung, die fuer sich genommen harmlos ist. Auf dem Server ist das
        beim ersten Export tatsaechlich eingetreten, weil der Export den
        Fixture-Anbieter erbte und der die Symbole der Watchlist nicht kennt.

        Das Ergebnis waere derselbe Schaden wie beim Datenbankabriss: ein
        vollstaendiges Manifest mit null Charts, und danach entfernt der
        Schreiber jede frueher exportierte Chartdatei als verwaist.
        """
        quellen, _ = quellen_mit(ohne_chart=frozenset({"AAPL", "MSFT"}))
        geflossen = []
        with pytest.raises(DashboardPublisherError, match="Keine einzige"):
            for datei in iter_snapshot(quellen):
                geflossen.append(datei.pfad)

        # **Der eigentliche Punkt, und er haengt an der Reihenfolge.** Der
        # Schreiber verbraucht den Generator traege; jede Datei, die vor dem
        # Abbruch herauskaeme, staende draussen schon geschrieben -- neben
        # dem alten Manifest, dessen Pruefsummen dann nicht mehr passen. Der
        # Browser wiese sie zurueck. Es darf deshalb keine geben.
        assert geflossen == []

    def test_ohne_aktien_ist_ein_baum_ohne_charts_in_ordnung(self) -> None:
        """Ein frisch aufgesetzter Server hat noch keine Aktien.

        Der Waechter darf die Abwesenheit von Aktien nicht mit dem Verlust
        ihrer Kursreihen verwechseln.
        """
        quellen, _ = quellen_mit(symbole=())
        manifest = json.loads(baum(quellen)[MANIFEST_PFAD].decode("utf-8"))
        assert manifest["counts"]["charts"] == 0

    def test_ein_datenbankabriss_bricht_den_export_ab(self) -> None:
        """Ausdruecklich anders als eine fehlende Kursreihe.

        Wer die Datenbank nicht lesen kann, weiss nicht, ob Charts fehlen --
        er weiss nur, dass er es nicht weiss. Liefe der Export durch, schriebe
        er ein vollstaendiges Manifest mit null Charts, und der Schreiber
        entfernte danach jede bisher exportierte Chartdatei als verwaist:
        Draussen stuende ein Stand, der wie ein regulaerer aussieht und keinen
        einzigen Chart hat.
        """
        quellen, _ = quellen_mit(bestand_nicht_lesbar=True)
        with pytest.raises(MarketDataUnavailableError):
            baum(quellen)


class TestDeterminismus:
    def test_zwei_laeufe_ergeben_dieselben_bytes(self) -> None:
        """Ohne diese Eigenschaft koennte der Upload nicht erkennen, was
        unveraendert blieb -- und lieferte jeden Lauf den ganzen Baum."""
        quellen, _ = quellen_mit(laeufe=(lauf(),))
        kennung = uuid.uuid4()
        zeit = datetime(2026, 9, 7, 21, 0, tzinfo=UTC)
        erst = baum(quellen, export_id=kennung, jetzt=zeit)
        zweit = baum(quellen, export_id=kennung, jetzt=zeit)
        assert erst == zweit

    def test_nur_das_manifest_aendert_sich_zwischen_zwei_exporten(self) -> None:
        quellen, _ = quellen_mit(laeufe=(lauf(),))
        erst = baum(quellen)
        zweit = baum(quellen)
        unterschiedlich = {pfad for pfad in erst if erst[pfad] != zweit[pfad]}
        assert unterschiedlich == {MANIFEST_PFAD}


class TestSchichtgrenze:
    def test_beide_schichten_meinen_dasselbe_manifest(self) -> None:
        """Die Infrastruktur darf die Praesentationsschicht nicht importieren
        und haelt den Pfad deshalb selbst. Zwei Konstanten, die auseinander
        laufen, ergaeben einen Klartextkopf, der auf eine Datei zeigt, die es
        nicht gibt -- und ein Dashboard, das gar nicht erst anfaengt."""
        assert MANIFEST_PFAD == MANIFEST_PFAD_INFRA
        assert SNAPSHOT_FORMAT == FORMAT_VERSION


class TestDateihashes:
    def test_das_manifest_nennt_je_pfad_den_hash_des_klartexts(self) -> None:
        """Der Schutz gegen eine untergeschobene aeltere Fassung.

        Sie entschluesselt sich einwandfrei -- sie gehoert ja zu diesem Baum
        -- und faellt erst am Hash auf.
        """
        quellen, _ = quellen_mit(laeufe=(lauf(),))
        dateien = baum(quellen)
        manifest = json.loads(dateien[MANIFEST_PFAD].decode("utf-8"))
        hashes = manifest["files"]

        # Jede Datei ausser dem Manifest selbst steht drin.
        assert set(hashes) == set(dateien) - {MANIFEST_PFAD}
        for pfad, erwartet in hashes.items():
            assert hashlib.sha256(dateien[pfad]).hexdigest() == erwartet

    def test_das_manifest_hasht_sich_nicht_selbst(self) -> None:
        """Es kann seinen eigenen Hash nicht enthalten -- und braucht ihn
        nicht: Wer es faelscht, faelscht die Verschluesselung mit."""
        quellen, _ = quellen_mit()
        manifest = json.loads(baum(quellen)[MANIFEST_PFAD].decode("utf-8"))
        assert MANIFEST_PFAD not in manifest["files"]


class TestEpisodenImExport:
    def test_der_backtest_je_aktie_fuehrt_die_episoden_je_auswertung(self) -> None:
        """Auch leer (ADR 0061): Eine Aktie ohne Auswertung seit der Umstellung
        hat eine leere Liste, keinen fehlenden Schluessel."""
        quellen, _ = quellen_mit()
        dateien = baum(quellen)
        inhalt = json.loads(dateien["data/stocks/AAPL/backtest.json"].decode("utf-8"))
        assert inhalt["episode_evaluations"] == []


class TestUebersichtenImExport:
    def test_die_aktienliste_und_der_signalbacktest_liegen_an_der_wurzel(self) -> None:
        """ADR 0062: eine Datei fuer alle Aktien statt eine je Aktie."""
        quellen, _ = quellen_mit()
        dateien = baum(quellen)
        aktien = json.loads(dateien["data/stocks.json"].decode("utf-8"))
        assert [a["symbol"] for a in aktien] == ["AAPL", "MSFT"]
        assert all(a["reports_count"] == 0 and a["last_report"] is None for a in aktien)
        ueberblick = json.loads(dateien["data/signal-backtests.json"].decode("utf-8"))
        assert ueberblick["stocks"] == []
        assert ueberblick["signal_rule_version"]

    def test_der_lauf_traegt_den_sperrstatus_als_rekonstruiert(self) -> None:
        ein_lauf = lauf()
        quellen, _ = quellen_mit(laeufe=(ein_lauf,))
        dateien = baum(quellen)
        detail = json.loads(dateien[f"data/analysis-runs/{ein_lauf.id}.json"].decode("utf-8"))
        assert detail["suppressed"] == []
        assert detail["suppression_window_days"] is None


class TestUnveraenderlicheLaeufe:
    """Abgeschlossene Läufe werden nicht jeden Abend neu gerechnet (ADR 0068).

    Der Export baute bisher **jeden je gelaufenen Lauf** und **je
    historischem Bericht eine eigene Abfrage** -- ein Anteil, der mit jedem
    Handelstag wächst, unabhängig davon, wieviel sich geändert hat.
    """

    UNVERAENDERLICH = ("data/analysis-runs/", "data/reports/")

    def _bekannt_aus(self, quellen: Exportquellen) -> dict[str, BekannteDatei]:
        """Der Stand, den ein vorangegangener Export hinterlassen hätte."""
        stand: dict[str, BekannteDatei] = {}
        for eintrag in eintraege(quellen):
            if eintrag.inhalt is None:
                continue
            stand[eintrag.pfad] = BekannteDatei(
                hash=hashlib.sha256(eintrag.inhalt).hexdigest(),
                fassung=eintrag.fassung,
            )
        return stand

    def _zweiter_export(self, quellen: Exportquellen) -> list[Exportdatei]:
        """Der zweite Export -- und die Wache, dass ueberhaupt etwas
        uebersprungen wurde.

        Ohne sie waere jede Zusicherung darunter auch dann erfuellt, wenn der
        Zwischenspeicher gar nicht griffe: Ein Baum ohne Uebersprung hat
        dieselben Pfade und dasselbe Manifest wie einer ohne
        Zwischenspeicher. Genau so ist dieser Block beim ersten Wurf gruen
        gewesen, obwohl nichts funktionierte.
        """
        zweite = eintraege(quellen, bekannt=self._bekannt_aus(quellen))
        assert [e for e in zweite if e.inhalt is None], (
            "nichts uebersprungen -- der Zwischenspeicher greift nicht"
        )
        return zweite

    def test_der_zweite_export_baut_die_laufdateien_nicht_erneut(self) -> None:
        quellen, _ = quellen_mit(laeufe=(lauf(),))

        uebersprungen = {e.pfad for e in self._zweiter_export(quellen) if e.inhalt is None}

        assert all(pfad.startswith(self.UNVERAENDERLICH) for pfad in uebersprungen)

    def test_charts_und_uebersichten_werden_immer_gebaut(self) -> None:
        """Sie ändern sich täglich. Ein Übersprung wäre dort falsch."""
        quellen, _ = quellen_mit(laeufe=(lauf(),))

        gebaut = {e.pfad for e in self._zweiter_export(quellen) if e.inhalt is not None}
        assert "data/stocks.json" in gebaut
        assert "data/analysis-runs.json" in gebaut
        assert any(pfad.endswith("/chart.json") for pfad in gebaut)

    def test_das_manifest_ist_dasselbe_wie_ohne_zwischenspeicher(self) -> None:
        """**Der Test, auf den es ankommt.**

        Das Manifest nennt je Pfad die Prüfsumme des Klartexts, und der
        Browser prüft sie nach dem Entschlüsseln. Käme sie beim Übersprung
        aus einer anderen Quelle als beim Bauen, fiele der Unterschied erst
        draußen auf -- als Datei, die sich entschlüsseln lässt und trotzdem
        abgewiesen wird.
        """
        quellen, _ = quellen_mit(laeufe=(lauf(),))
        kennung = uuid.uuid4()
        zeit = datetime(2026, 9, 20, 21, 0, tzinfo=UTC)
        bekannt = self._bekannt_aus(quellen)

        self._zweiter_export(quellen)  # Wache: es wird wirklich uebersprungen
        ohne = baum(quellen, export_id=kennung, jetzt=zeit)
        mit = baum(quellen, export_id=kennung, jetzt=zeit, bekannt=bekannt)

        assert json.loads(ohne[MANIFEST_PFAD]) == json.loads(mit[MANIFEST_PFAD])

    def test_dieselben_pfade_wie_ohne_zwischenspeicher(self) -> None:
        """Kein Pfad faellt weg -- sonst raeumte der Schreiber ihn als
        verwaist weg, und draussen fehlte er."""
        quellen, _ = quellen_mit(laeufe=(lauf(),))

        ohne = [e.pfad for e in eintraege(quellen)]
        mit = [e.pfad for e in self._zweiter_export(quellen)]

        assert ohne == mit

    def test_eine_andere_fassung_wird_neu_gerechnet(self) -> None:
        """Ändert sich die Form einer exportierten Datei, ist der bekannte
        Stand wertlos -- und das fällt von selbst auf, weil die Fassung über
        die Schemata der Antwortmodelle gebildet wird."""
        quellen, _ = quellen_mit(laeufe=(lauf(),))
        veraltet = {
            pfad: BekannteDatei(hash=eintrag.hash, fassung="aus-einer-anderen-zeit")
            for pfad, eintrag in self._bekannt_aus(quellen).items()
        }

        zweite = eintraege(quellen, bekannt=veraltet)

        assert not [e for e in zweite if e.inhalt is None]

    def test_ein_unbekannter_pfad_wird_gerechnet(self) -> None:
        """Der Fall nach einem verlorenen Zustand: alles neu, nur langsamer."""
        quellen, _ = quellen_mit(laeufe=(lauf(),))

        zweite = eintraege(quellen, bekannt={})

        assert not [e for e in zweite if e.inhalt is None]

    def test_die_fassung_haengt_am_schema_der_modelle(self) -> None:
        """Sie ist abgeleitet und nicht gepflegt: Eine Nummer, an die jemand
        denken muss, wird irgendwann vergessen -- und der Fehler wäre still."""
        assert len(EXPORT_FASSUNG) == 16
        assert EXPORT_FASSUNG == _export_fassung()
