"""Der Datenbaum eines Snapshots -- Pfad und Inhalt je Datei (ADR 0060).

Der Aufbau steht im Spike-Bericht, Abschnitt 8.2. Zwei Eigenschaften sind
dabei die wichtigen:

**Keine zweite Wahrheit.** Jede Datei enthaelt die Antwort des jeweiligen
Endpunkts, gebaut von ``presentation.api.views`` -- demselben Code, den die
API benutzt. Ein eigener Zusammenbau fuer den Export haette dieselben Zahlen
ein zweites Mal berechnet, und zwei Rechnungen laufen auseinander.

**Der Snapshot ist eine Aufzaehlung, kein Verzeichnisbaum.** Diese Ebene
kennt weder Dateisystem noch Verschluesselung noch Anbieter: Sie liefert
Pfad und Bytes. Was damit geschieht -- schreiben, verschluesseln, hochladen
-- entscheidet der Aufrufer. Das ist die Naht, an der Stufe 2 die
Schreibfunktion austauscht, ohne dass hier etwas anzufassen waere.

Der Snapshot ist **deterministisch**: Derselbe Datenbestand ergibt Byte fuer
Byte dieselben Dateien. Nur das Manifest traegt Zeitpunkt und Kennung des
Exports und aendert sich mit jedem Lauf. Ohne diese Eigenschaft koennte der
Upload nicht erkennen, was unveraendert blieb.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from ai_trading_analyst import __version__ as anwendungsversion
from ai_trading_analyst.application.read_run_overview import ReadRunOverviewUseCase
from ai_trading_analyst.domain.analysis import (
    MarketDataProvider,
    MarketDataProviderError,
    MarketDataUnavailableError,
    RepeatSuppressionParameters,
    UnitOfWork,
)
from ai_trading_analyst.domain.backtesting import BacktestParameters
from ai_trading_analyst.domain.report import REPORT_SCHEMA_VERSION
from ai_trading_analyst.domain.scheduling import DashboardPublisherError
from ai_trading_analyst.domain.screening import SIGNAL_RULE_VERSION, CandidateRuleParameters
from ai_trading_analyst.observability.logging_setup import get_logger
from ai_trading_analyst.observability.timing import Zeitkonto
from ai_trading_analyst.presentation.api import views
from ai_trading_analyst.presentation.api.schemas import (
    AnalysisRunDetailResponse,
    AnalysisRunResponse,
    ReportSummaryResponse,
)
from ai_trading_analyst.presentation.validation_chart import build_chart_payload

_logger = get_logger(__name__)

SNAPSHOT_FORMAT = 1
"""Formatversion des Datenbaums.

Sie steht von Anfang an im Manifest, obwohl es erst eine Fassung gibt: Eine
Oberflaeche, die einen Datenbaum ohne Formatangabe vorfindet, kann nicht
zwischen "alte Fassung" und "beschaedigt" unterscheiden.

Ausdruecklich **kein** Schalter fuer das Verschluesselungsverfahren -- das
ist Eigenschaft des Builds (ADR 0060, Entscheidung Punkt 6). Stuende es
hier, koennte wer das Manifest schreiben darf auf Klartext zurueckschalten.
"""

MANIFEST_PFAD = "data/manifest.json"

_FASSUNG_SALZ = "1"
"""Von Hand zu erhoehen, wenn sich die **Rechnung** hinter einer der
unveraenderlichen Pfadfamilien aendert, ohne dass sich ihre Form aendert
(ADR 0068, Punkt 3).

Der haeufigere Fall -- eine geaenderte Form -- faellt von selbst auf, weil
``EXPORT_FASSUNG`` ueber die Schemata der Antwortmodelle gebildet wird. Eine
geaenderte Rechnung bei gleicher Form tut das nicht: Wer etwa ``_gesperrte``
korrigiert, erhoeht diesen Wert -- oder faehrt einmal ``publish --full``.
"""


def _export_fassung() -> str:
    """Die Kennung, unter der eine unveraenderliche Datei entstanden ist.

    Abgeleitet statt gepflegt: Eine Fassungsnummer, an die jemand denken
    muss, wird irgendwann vergessen, und der Fehler waere still -- das
    Dashboard zeigte fuer die Historie das alte Format und fuer heute das
    neue. Das Schema der beteiligten Modelle zu hashen macht diesen Fall
    selbsttragend.
    """
    schemata = json.dumps(
        [
            AnalysisRunDetailResponse.model_json_schema(),
            ReportSummaryResponse.model_json_schema(),
            REPORT_SCHEMA_VERSION,
            _FASSUNG_SALZ,
        ],
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(schemata.encode("utf-8")).hexdigest()[:16]


EXPORT_FASSUNG = _export_fassung()

_SEITE = 200
"""Wie viele Laeufe je Abfrage geladen werden. Nur eine Speichergrenze."""


@dataclass(frozen=True, slots=True)
class Exportdatei:
    """Eine Datei des Datenbaums: kanonischer Pfad und fertige Bytes.

    Der Pfad ist zugleich Teil der Zusatzdaten der Verschluesselung in
    Stufe 2 -- eine Datei, die unter einem anderen Pfad auftaucht, laesst
    sich dort nicht mehr entschluesseln (Vertauschungsschutz). Deshalb ist er
    kanonisch und nicht plattformabhaengig: immer mit ``/``, immer beginnend
    mit ``data/``.
    """

    pfad: str
    inhalt: bytes | None
    """``None`` heisst **unveraendert** (ADR 0068).

    Die Datei wurde gar nicht erst gebaut, weil sie aus unveraenderlichen
    Zeilen entsteht und unter derselben Fassung schon einmal entstanden ist.
    Der Schreiber uebernimmt Pruefsumme und Zielnamen aus dem bekannten
    Stand.
    """
    fassung: str | None = None
    """Unter welcher Fassung der Inhalt entstand -- nur fuer die
    unveraenderlichen Pfadfamilien gesetzt."""


@dataclass(frozen=True, slots=True)
class BekannteDatei:
    """Was ueber eine Datei des letzten Standes bekannt ist (ADR 0068).

    Bewusst **kein** Import aus der Infrastruktur: Die Praesentationsschicht
    kennt den Verzeichnisschreiber nicht (Doc 10, Paragraph 9). Der
    Composition Root uebersetzt.
    """

    hash: str
    fassung: str | None


@dataclass(frozen=True, slots=True)
class Exportquellen:
    """Woraus der Snapshot entsteht.

    Dieselben Bausteine, die auch die API im ``app.state`` haelt. Der
    Marktdatenanbieter kommt als **Fabrik**, weil er an der Watchlist-Datei
    haengt und erst gebraucht wird, wenn die Charts an der Reihe sind -- also
    nach allem, was ohne ihn entsteht.

    **Ein fehlendes Watchlist-Verzeichnis bricht den Export ab**, und zwar
    ganz: Die Fabrik wird ausserhalb jeder Fehlerbehandlung gerufen, und ihr
    ``WatchlistError`` ist kein ``MarketDataProviderError``. Das ist richtig
    so -- ohne Watchlist ist der Bestand nicht zu deuten --, aber es ist
    etwas anderes als "kostet nur den Chart". Im Tageslauf faengt es die
    Isolation des Exportschritts ab, in der Kommandozeile die Behandlung in
    ``main``.
    """

    uow_factory: Callable[[], UnitOfWork]
    backtest_parameters: BacktestParameters
    candidate_rule_parameters: CandidateRuleParameters
    chart_market_data: Callable[[], MarketDataProvider]
    repeat_suppression: RepeatSuppressionParameters | None = None
    """Fuer den rekonstruierten Sperrstatus je Lauf (ADR 0062). Ohne die
    Parameter bleibt die Liste leer -- als "nicht gerechnet", was das
    Manifestfeld ``suppression_window_days: null`` dem Leser sagt."""
    market_timezone: str = "America/New_York"


_UNSICHER = re.compile(r"[^A-Za-z0-9_-]")


def dateisicherer_name(symbol: str) -> str:
    """Ein Symbol als Verzeichnisname.

    ``BRK B`` und ``BF.B`` sind gueltige Symbole und keine gueltigen
    Pfadbestandteile auf allen Systemen -- Windows mag den Punkt am Ende
    nicht, ein Leerzeichen macht jede Kommandozeile unleserlich. Ersetzt wird
    deshalb alles ausserhalb von Buchstaben, Ziffern, ``_`` und ``-``.

    Die Abbildung Symbol -> Name steht im Manifest, damit die Oberflaeche
    nicht dieselbe Regel ein zweites Mal umsetzen muss. In Stufe 2 sind alle
    Namen ohnehin opak, und die Abbildung liegt im verschluesselten Manifest.
    """
    ersetzt = _UNSICHER.sub("-", symbol.strip().upper())
    return ersetzt or "-"


def _symbolnamen(symbole: Sequence[str]) -> dict[str, str]:
    """Symbol -> Verzeichnisname, kollisionsfrei und stabil.

    ``BRK B`` und ``BRK-B`` ergaeben denselben Namen. Der zweite bekommt
    deshalb eine Nummer angehaengt -- vergeben in alphabetischer Reihenfolge
    der Symbole, damit derselbe Bestand immer dieselben Namen ergibt. Zwei
    Exporte, die dieselbe Aktie unter verschiedenen Namen ablegen, waeren
    zwei Datenbaeume und kein Snapshot.
    """
    vergeben: dict[str, str] = {}
    belegt: set[str] = set()
    for symbol in sorted(symbole):
        name = dateisicherer_name(symbol)
        if name in belegt:
            nummer = 2
            while f"{name}-{nummer}" in belegt:
                nummer += 1
            name = f"{name}-{nummer}"
        belegt.add(name)
        vergeben[symbol] = name
    return vergeben


def _als_json(nutzlast: Any) -> bytes:
    """JSON in der Fassung, die auch die API schickt.

    ``ensure_ascii=False``: Die Berichte sind deutsch, und ``\\u00e4`` statt
    ``ä`` blaehte den Export ohne Gewinn. ``sort_keys`` bleibt aus -- das
    Berichtsdokument geht unveraendert hinaus (ADR 0039), und eine
    umsortierte Abschnittsfolge waere eine Veraenderung.
    """
    return json.dumps(nutzlast, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _modelle(modelle: Sequence[BaseModel]) -> list[dict[str, Any]]:
    return [modell.model_dump(mode="json") for modell in modelle]


def _modell(antwort: BaseModel) -> bytes:
    return _als_json(antwort.model_dump(mode="json"))


def _alle_laeufe(uow: UnitOfWork) -> list[AnalysisRunResponse]:
    """Alle Laeufe, neueste zuerst -- seitenweise geladen.

    Das Repository bietet bewusst kein ``list_all`` (die Zahl waechst mit
    jedem Handelstag). Hier wird trotzdem alles gebraucht, weil die
    Oberflaeche ausserhalb selbst blaettert; geladen wird deshalb in Seiten
    und nicht in einem Zug.
    """
    gesammelt: list[AnalysisRunResponse] = []
    offset = 0
    while True:
        seite = views.analysis_run_page(uow, limit=_SEITE, offset=offset)
        gesammelt.extend(seite.items)
        if len(seite.items) < _SEITE or len(gesammelt) >= seite.total:
            return gesammelt
        offset += _SEITE


def _alle_berichte(uow: UnitOfWork, symbol: str) -> list[ReportSummaryResponse]:
    """Die ganze Historie einer Aktie -- seitenweise geladen.

    **Vollstaendig und nicht die erste Seite.** Draussen blaettert die
    Oberflaeche selbst und rechnet die Gesamtzahl aus dem, was in der Datei
    steht; eine gedeckelte Datei ergaebe dort eine falsche Gesamtzahl und eine
    abgeschnittene Historie, ohne dass irgendwo stuende, dass gekuerzt wurde.
    Genau das schliesst der Grundsatz "keine stille Auslassung" aus.
    """
    gesammelt: list[ReportSummaryResponse] = []
    offset = 0
    while True:
        seite = views.reports_of_stock(uow, symbol, limit=_SEITE, offset=offset)
        gesammelt.extend(seite.items)
        if len(seite.items) < _SEITE or len(gesammelt) >= seite.total:
            return gesammelt
        offset += _SEITE


def iter_snapshot(
    quellen: Exportquellen,
    *,
    export_id: UUID | None = None,
    jetzt: datetime | None = None,
    bekannt: Mapping[str, BekannteDatei] | None = None,
) -> Iterator[Exportdatei]:
    """Der vollstaendige Datenbaum, Datei fuer Datei.

    Ein Generator und keine Liste: Der Vollexport ist gemessen rund 75 MB
    roh, und ihn erst vollstaendig im Speicher aufzubauen, um ihn danach zu
    schreiben, waere auf dem Handelsrechner die falsche Sparsamkeit.

    **Das Manifest kommt zuletzt.** Es zaehlt, was tatsaechlich entstanden
    ist -- und ein abgebrochener Export hinterlaesst damit keinen Stand,
    statt einen unvollstaendigen zu behaupten.

    ``bekannt`` sind die Dateien des letzten Standes, deren Zieldatei noch
    liegt (ADR 0068). Was daraus unter derselben Fassung stammt und zu einer
    unveraenderlichen Pfadfamilie gehoert, wird nicht neu gerechnet.
    """
    kennung = export_id if export_id is not None else uuid4()
    zeitpunkt = jetzt if jetzt is not None else datetime.now(UTC)

    berichte_gesamt = 0
    charts_gesamt = 0
    fehlende_charts: list[str] = []
    hashes: dict[str, str] = {}
    # **Nicht ``gemessen`` um die Schleifen herum**: Diese Funktion ist ein
    # Generator, und zwischen zwei ``yield`` ist sie angehalten. Eine Messung
    # ueber die Schleife naehme die Zeit des Verbrauchers mit -- also das
    # Verschluesseln und Schreiben, nicht das Rechnen, um das es geht.
    konto = Zeitkonto()
    vorstand = bekannt if bekannt is not None else {}
    uebersprungen = 0

    def unveraendert(pfad: str) -> Exportdatei | None:
        """Die Datei, falls sie unter derselben Fassung schon existiert.

        Die Pruefsumme kommt dann aus dem bekannten Stand statt aus dem
        Inhalt -- sie ist dieselbe, und genau das ist der Punkt: Das
        Manifest bleibt vollstaendig, ohne dass die Datei entstehen muss.
        """
        eintrag = vorstand.get(pfad)
        if eintrag is None or eintrag.fassung != EXPORT_FASSUNG:
            return None
        hashes[pfad] = eintrag.hash
        return Exportdatei(pfad, None, EXPORT_FASSUNG)

    def datei(pfad: str, inhalt: bytes, fassung: str | None = None) -> Exportdatei:
        """Merkt sich den Hash und liefert die Datei.

        Die Hashes stehen danach im Manifest, und der Browser prueft sie nach
        dem Entschluesseln. Das ist der Schutz gegen eine untergeschobene
        aeltere Fassung einer einzelnen Datei: Sie entschluesselt sich
        einwandfrei -- sie gehoert ja zu diesem Baum -- und faellt erst am
        Hash auf.
        """
        hashes[pfad] = hashlib.sha256(inhalt).hexdigest()
        return Exportdatei(pfad, inhalt, fassung)

    # **Die Charts kommen zuerst, und das ist kein Geschmack.** Der Schreiber
    # verbraucht diesen Generator traege: Jede Datei, die hier vor einem
    # Abbruch herausgereicht wurde, steht draussen bereits geschrieben --
    # neben dem *alten* Manifest, dessen Pruefsummen dann nicht mehr passen.
    # Der Browser wiese sie zurueck, und das Dashboard waere unbrauchbar
    # statt nur veraltet. Faellt der Waechter unten, ist deshalb noch keine
    # einzige Datei geflossen.
    #
    # Die eigene, kurze Transaktion dafuer: Die Charts selbst laufen
    # ausserhalb einer Unit of Work -- der Anbieter liest den Bestand selbst,
    # und eine Transaktion ueber zweihundert Kursreihen und eine
    # Viertelstunde offen zu halten waere eine lange Sperre ohne Gegenwert.
    with quellen.uow_factory() as uow:
        aktien = list(uow.stocks.list_all())  # alphabetisch, wie das Repository liefert
    symbole = [stock.symbol for stock in aktien]
    namen = _symbolnamen(symbole)

    # Die Charts ausserhalb der Unit of Work: Der Anbieter liest den Bestand
    # selbst, und eine Transaktion ueber zweihundert Kursreihen offen zu
    # halten waere eine lange Sperre ohne Gegenwert. Die Aktien selbst liegen
    # schon vor -- es sind Domain-Objekte ohne Sitzungsbindung, und sie
    # zweihundertmal erneut nachzuschlagen brauchte eine zweite Transaktion
    # fuer nichts.
    marktdaten = quellen.chart_market_data()
    for aktie in aktien:
        symbol = aktie.symbol
        try:
            with konto.bei("chart_kerzenserie"):
                reihe = marktdaten.get_candle_series(aktie)
        except MarketDataUnavailableError:
            # **Zuerst der Ausfall, und die Reihenfolge ist der ganze
            # Punkt:** ``MarketDataUnavailableError`` ist Unterklasse von
            # ``MarketDataProviderError``. Stuende die breite Klausel
            # zuerst, finge sie den Datenbankabriss mit -- und der Export
            # schriebe ein vollstaendiges Manifest mit null Charts, worauf
            # der Schreiber jede bisher exportierte Chartdatei als
            # verwaist entfernte. Draussen stuende dann ein Stand, der wie
            # ein regulaerer aussieht und keinen einzigen Chart hat.
            # Dieselbe Reihenfolge wie im Endpunkt (``api/v1/stocks.py``).
            raise
        except MarketDataProviderError as fehler:
            # Eine Aktie ohne Kerzen im Bestand kostet dagegen nur ihren
            # Chart. Das ist eine Aussage ueber die Datenlage, kein
            # Betriebsproblem, und sie steht im Manifest.
            _logger.warning("Kein Chart fuer %s im Export: %s", symbol, fehler)
            fehlende_charts.append(symbol)
            continue
        charts_gesamt += 1
        with konto.bei("chart_aufbau"):
            chart = _als_json(
                build_chart_payload(symbol, reihe, quellen.candidate_rule_parameters)
            )
        yield datei(f"data/stocks/{namen[symbol]}/chart.json", chart)

    if aktien and charts_gesamt == 0:
        # **Vor dem Manifest, und deshalb vor dem gueltigen Stand.** Jede
        # einzelne Aktie hat hier ihren Chart verloren, und keine davon hat
        # den Ausfall gemeldet, der oben zum Abbruch fuehrt. Das ist keine
        # Aussage ueber die Datenlage mehr, sondern ueber die Konfiguration:
        # ein Bestand ohne Kerzen, oder ein Anbieter, der keine liefert.
        #
        # Ohne diesen Abbruch entstuende genau der Stand, den die Klausel
        # darueber verhindert -- nur auf dem anderen Weg dorthin: ein
        # vollstaendiges Manifest ohne einen einzigen Chart, worauf der
        # Schreiber alle frueher exportierten Charts als verwaist entfernt.
        #
        # **Die Entscheidung dahinter heisst: lieber gar nichts als etwas
        # ohne Charts.** Es geht dann auch nichts hinaus, was fuer sich
        # tadellos waere -- Laeufe, Berichte, Backtests. Das ist gewollt: Ein
        # Dashboard, dem jede Kursreihe fehlt, ist kein magerer Stand,
        # sondern ein irrefuehrender.
        raise DashboardPublisherError(
            f"Keine einzige der {len(aktien)} Aktien hat eine Kerzenreihe geliefert. "
            "Der Export bricht ab, statt einen Stand ohne Charts zu schreiben. "
            "Zu pruefen: ist der Bestand gefuellt (Backfill), und passt die "
            "Watchlist zu den Aktien in der Datenbank -- die Kerzen kommen aus "
            "dem Bestand, die Kontrakte aber aus der Watchlist. Danach "
            "'publish --full'."
        )

    with quellen.uow_factory() as uow:
        laeufe = _alle_laeufe(uow)
        yield datei(
            "data/analysis-runs.json",
            _als_json(_modelle(laeufe)),
        )

        uebersicht = ReadRunOverviewUseCase(
            quellen.uow_factory,
            repeat_suppression=quellen.repeat_suppression,
            market_timezone=quellen.market_timezone,
        )
        for lauf in laeufe:
            lauf_id = lauf.id

            # **Drei unveraenderliche Pfadfamilien** (ADR 0068). Sie
            # entstehen aus Zeilen, die ein abgeschlossener Lauf nicht mehr
            # aendert; sie jeden Abend neu zu rechnen ist Arbeit ohne
            # moeglichen Unterschied im Ergebnis. Die Kurzliste wird dabei
            # auch dann gebraucht, wenn ihre *Datei* uebersprungen wird --
            # die Berichte darunter haengen an ihr.
            ansicht_pfad = f"data/analysis-runs/{lauf_id}.json"
            schon_da = unveraendert(ansicht_pfad)
            if schon_da is not None:
                uebersprungen += 1
                yield schon_da
            else:
                with konto.bei("lauf_uebersicht"):
                    detail = uebersicht.execute(lauf_id)
                    inhalt = (
                        None
                        if detail is None
                        else _modell(AnalysisRunDetailResponse.from_overview(detail))
                    )
                if inhalt is not None:
                    yield datei(ansicht_pfad, inhalt, EXPORT_FASSUNG)

            with konto.bei("lauf_kurzliste"):
                kurzliste = views.reports_of_run(uow, lauf_id)
            kurzliste_pfad = f"data/analysis-runs/{lauf_id}/reports.json"
            schon_da = unveraendert(kurzliste_pfad)
            if schon_da is not None:
                uebersprungen += 1
                yield schon_da
            else:
                with konto.bei("lauf_kurzliste_json"):
                    kurzliste_json = _als_json(_modelle(kurzliste))
                yield datei(kurzliste_pfad, kurzliste_json, EXPORT_FASSUNG)

            for eintrag in kurzliste:
                bericht_pfad = f"data/reports/{eintrag.report_id}.json"
                schon_da = unveraendert(bericht_pfad)
                if schon_da is not None:
                    berichte_gesamt += 1
                    uebersprungen += 1
                    yield schon_da
                    continue
                with konto.bei("bericht"):
                    bericht = uow.stock_reports.get(eintrag.report_id)
                    # Das gespeicherte Dokument, unveraendert (ADR 0039).
                    dokument = None if bericht is None else _als_json(dict(bericht.document))
                if bericht is None or dokument is None:
                    continue
                berichte_gesamt += 1
                # Derselbe Ausdruck wie bei der Pruefung oben: ``bericht.id``
                # und ``eintrag.report_id`` sind dasselbe, aber zwei
                # Schreibweisen desselben Pfades laden zum Auseinanderlaufen
                # ein -- und ein abweichender Pfad hiesse, dass der
                # Uebersprung ins Leere greift.
                yield datei(bericht_pfad, dokument, EXPORT_FASSUNG)

        # Die zwei Uebersichten (ADR 0062): eine Datei fuer alle Aktien statt
        # zweihundert Einzeldateien je Listenansicht.
        with konto.bei("uebersichten"):
            stocks_json = _als_json(_modelle(views.stock_index(uow)))
            signale_json = _modell(views.signal_backtest_overview(uow))
        yield datei("data/stocks.json", stocks_json)
        yield datei("data/signal-backtests.json", signale_json)

        messungen = views.measurements(uow)
        yield datei(
            "data/options-backtests.json",
            _als_json(_modelle(messungen)),
        )
        for messung in messungen:
            messung_id = messung.measurement_id
            with konto.bei("optionsmessung"):
                messung_json = _modell(
                    views.measurement_detail(
                        uow, messung_id, backtest_params=quellen.backtest_parameters
                    )
                )
            yield datei(f"data/options-backtests/{messung_id}.json", messung_json)

        for symbol in symbole:
            name = namen[symbol]
            with konto.bei("aktie_berichtsliste"):
                liste_json = _als_json(_modelle(_alle_berichte(uow, symbol)))
            yield datei(f"data/stocks/{name}/reports.json", liste_json)
            with konto.bei("aktie_backtest"):
                backtest_json = _modell(
                    views.stock_backtest(
                        uow,
                        symbol,
                        measurement_id=None,
                        backtest_params=quellen.backtest_parameters,
                    )
                )
            yield datei(f"data/stocks/{name}/backtest.json", backtest_json)

    konto.protokolliere(
        _logger,
        "export_zerlegung",
        aktien=len(aktien),
        laeufe=len(laeufe),
        berichte=berichte_gesamt,
        uebersprungen=uebersprungen,
    )
    yield Exportdatei(
        MANIFEST_PFAD,
        _als_json(
            _manifest(
                export_id=kennung,
                zeitpunkt=zeitpunkt,
                laeufe=laeufe,
                namen=namen,
                berichte=berichte_gesamt,
                messungen=len(messungen),
                charts=charts_gesamt,
                fehlende_charts=fehlende_charts,
                hashes=hashes,
            )
        ),
    )


def _manifest(
    *,
    export_id: UUID,
    zeitpunkt: datetime,
    laeufe: Sequence[AnalysisRunResponse],
    namen: Mapping[str, str],
    berichte: int,
    messungen: int,
    charts: int,
    fehlende_charts: Sequence[str],
    hashes: Mapping[str, str],
) -> dict[str, Any]:
    """Was die Oberflaeche ueber diesen Stand wissen muss.

    Die Pflichtanzeige "Stand: Lauf vom ..., exportiert ..." haengt daran:
    **Ein alter Stand muss alt aussehen.** Ein Dashboard, das gestrige Zahlen
    zeigt, ohne es zu sagen, ist gefaehrlicher als eines, das gar nichts
    zeigt -- der Server koennte seit Tagen stehen.

    ``fehlende_charts`` steht ausdruecklich drin: Ohne die Liste saehe eine
    Aktie ohne Kursreihe im Bestand aus wie eine, deren Datei beim Hochladen
    verloren ging.
    """
    juengster = laeufe[0] if laeufe else None
    return {
        "format": SNAPSHOT_FORMAT,
        "export_id": str(export_id),
        "exported_at": zeitpunkt.isoformat(),
        "run_id": str(juengster.id) if juengster is not None else None,
        "run_started_at": juengster.started_at.isoformat() if juengster is not None else None,
        "run_completed_at": (
            juengster.completed_at.isoformat()
            if juengster is not None and juengster.completed_at is not None
            else None
        ),
        "run_status": juengster.status.value if juengster is not None else None,
        "application_version": anwendungsversion,
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "signal_rule_version": SIGNAL_RULE_VERSION,
        "symbols": dict(namen),
        "counts": {
            "runs": len(laeufe),
            "reports": berichte,
            "stocks": len(namen),
            "charts": charts,
            "measurements": messungen,
        },
        "stocks_without_chart": list(fehlende_charts),
        # SHA-256 des Klartexts je Pfad. Der Browser prueft sie nach dem
        # Entschluesseln; das faengt die untergeschobene aeltere Fassung einer
        # einzelnen Datei, die sich einwandfrei entschluesselt, weil sie zu
        # diesem Baum gehoert. Was damit **nicht** zu fangen ist: das
        # Zurueckspielen des ganzen Standes samt Manifest -- dagegen hilft nur,
        # dass die Oberflaeche den Stand anzeigt.
        "files": dict(sorted(hashes.items())),
    }
