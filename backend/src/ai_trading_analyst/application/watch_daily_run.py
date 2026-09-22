"""Der Waechter: Lief heute ein Lauf, und griff die Sicherung? (ADR 0071)

**Er sitzt ausserhalb des Vorgangs, den er ueberwacht.** Das ist der ganze
Punkt. Der Tageslauf meldet seinen eigenen Ausfall zuverlaessig, solange er
ueberhaupt bis zu seiner Meldelogik kommt -- und genau dort liegen seine
blinden Flecken:

* Ein fehlerhafter Argumentstring oder ein fehlendes Geheimnis beenden das
  Programm mit Rueckgabewert 2, **bevor** eine Zeile des Dispatchers laeuft.
  Am 2026-09-22 hat das einen Handelstag gekostet: 17 Startversuche, keine
  Zeile in ``dispatcher_runs``, keine Meldung.
* Startet die Aufgabenplanung gar nicht -- Server aus, Aufgabe deaktiviert
  und nicht wieder eingeschaltet --, gibt es nichts, was sich melden koennte.
* Ein *haengender* Lauf haelt den Advisory Lock. Alle weiteren Starts enden
  bei ``IN_PROGRESS``, und weil die Ueberfaelligkeitsmeldung innerhalb der
  Sperre laeuft, geht auch sie nicht hinaus.

Ein Waechter im ueberwachten Prozess schweigt in allen drei Faellen. Dieser
hier liest nur den Bestand und die Sicherungsablage, braucht weder TWS noch
Watchlist noch Modellzugang, und laeuft als eigene Aufgabe.

**Er meldet, er behebt nichts.** Ein Waechter, der Laeufe nachstartet, waere
ein zweiter Dispatcher mit eigenen Fehlern.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from ..domain.scheduling.models import (
    DailyRunSummary,
    DispatchDecision,
    SchedulerParameters,
    assumed_session,
    scheduled_run_for,
)
from ..domain.scheduling.ports import DailyRunLookup, Notifier, NotifierError

_logger = logging.getLogger(__name__)

MELDUNGSTITEL = "Waechter"

LAUF_HOECHSTDAUER = timedelta(hours=3)
"""Ab wann ein Lauf auf 'running' als haengend gilt.

Dieselbe Grenze wie das Zeitlimit der geplanten Aufgabe (Doc 14): Was
laenger laeuft, haette der Aufgabenplaner ohnehin abbrechen sollen. Ein
regulaerer Lauf dauert rund 103 Minuten.
"""

SICHERUNG_HOECHSTALTER = timedelta(hours=26)
"""Ab wann eine Sicherung als ausgeblieben gilt.

Sechsundzwanzig und nicht vierundzwanzig Stunden: Die Sicherung laeuft
taeglich zur selben Zeit, und zwei Laeufe liegen deshalb fast genau 24
Stunden auseinander. Bei glatten 24 Stunden meldete schon eine um Minuten
verschobene Ausfuehrung einen Ausfall. Zwei Stunden Luft lassen genau einen
ausgefallenen Tag auffallen und keinen puenktlichen.
"""


@dataclass(frozen=True, slots=True)
class WatchdogReport:
    """Was der Waechter vorgefunden hat."""

    findings: tuple[str, ...] = ()
    notified: bool = False
    """Ob die Meldung zugestellt wurde. ``False`` bei Befunden heisst: Der
    Kanal war nicht erreichbar -- der schlechteste Fall, denn dann weiss
    niemand etwas."""

    @property
    def conspicuous(self) -> bool:
        return bool(self.findings)


class WatchDailyRunUseCase:
    """Prueft den abgelaufenen Handelstag und meldet, was fehlt."""

    def __init__(
        self,
        *,
        runs: DailyRunLookup,
        parameters: SchedulerParameters,
        notifier: Notifier | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        latest_backup: Callable[[], datetime | None] | None = None,
        max_backup_age: timedelta = SICHERUNG_HOECHSTALTER,
        max_run_duration: timedelta = LAUF_HOECHSTDAUER,
    ) -> None:
        self._runs = runs
        self._parameters = parameters
        self._notifier = notifier
        self._now = now
        self._latest_backup = latest_backup
        self._max_backup_age = max_backup_age
        self._max_run_duration = max_run_duration

    def execute(self) -> WatchdogReport:
        jetzt = self._now().astimezone(ZoneInfo(self._parameters.timezone))
        befunde = [*self._pruefe_lauf(jetzt), *self._pruefe_sicherung(jetzt)]
        if not befunde:
            return WatchdogReport()
        return WatchdogReport(findings=tuple(befunde), notified=self._melde(befunde, jetzt))

    def _pruefe_lauf(self, jetzt: datetime) -> list[str]:
        """Gab es heute einen erledigten Lauf?

        Der Boersenkalender bleibt aussen vor -- er kommt von der TWS, und ein
        Waechter, der erst die TWS braucht, waere genau dann stumm, wenn er
        reden soll. Stattdessen die Wochentagsnaeherung aus ``assumed_session``
        mit derselben Begruendung wie dort: Faellt der Tag in Wahrheit auf
        einen Feiertag, entsteht eine Meldung zu viel. Die umgekehrte
        Verwechslung waere schlimmer.
        """
        boersentag = jetzt.date()
        session = assumed_session(boersentag, self._parameters)
        if session is None:
            return []
        geplant = scheduled_run_for(session, self._parameters)
        if geplant is None:
            return []

        # **Erst nach Fristablauf.** Sonst meldete ein Waechter, der aus
        # Versehen mittags laeuft, einen Lauf als ausgefallen, der noch gar
        # nicht faellig ist.
        if geplant.decide(jetzt) is not DispatchDecision.TOO_LATE:
            return []

        lage = self._runs.summary_on(boersentag)
        if lage.succeeded:
            return []

        # **Der Dispatcher hat schon geredet.** Dann weiss der Nutzer Bescheid,
        # und eine zweite Meldung derselben Sache waere nur Laerm -- der
        # Waechter faengt, was *keiner* meldet, nicht was schon gemeldet ist.
        if lage.alerted:
            return []

        if lage.running:
            return self._haengender_lauf(lage, jetzt)

        if not lage.started:
            return [
                f"Fuer {boersentag.isoformat()} gibt es keinen einzigen Versuch. "
                "Entweder die Aufgabenplanung hat nicht gestartet, oder der Start "
                "ist vor dem Programm gescheitert -- Rueckgabewert 2 in der Spalte "
                "'Letztes Ausfuehrungsergebnis' deutet auf einen fehlerhaften "
                "Argumentstring. Falls heute ein Boersenfeiertag war, ist dies "
                "ein Fehlalarm."
            ]
        fehler = lage.last_error or "ohne Angabe"
        return [
            f"Fuer {boersentag.isoformat()} gibt es {lage.attempts} Versuch(e), "
            f"aber keinen erledigten Lauf. Letzter Fehler: {fehler}"
        ]

    def _haengender_lauf(self, lage: DailyRunSummary, jetzt: datetime) -> list[str]:
        """Laeuft er noch, oder haengt er?

        Ein Lauf dauert seit dem Export-Umbau rund 103 Minuten und darf bis
        gegen 23:15 arbeiten -- er ist um diese Zeit also voellig regulaer
        unterwegs. Ihn dann zu melden waere ein taeglicher Fehlalarm.

        Haengt er dagegen, haelt er den Advisory Lock, alle weiteren Starts
        enden bei ``IN_PROGRESS``, und weil die Ueberfaelligkeitsmeldung des
        Dispatchers **innerhalb** der Sperre laeuft, geht auch sie nie hinaus.
        Das ist der dritte blinde Fleck aus AUDIT-003-014, und nur der
        Waechter kann ihn sehen.

        Die Grenze ist dieselbe wie das Zeitlimit der Aufgabe (Doc 14): Was
        laenger laeuft, haette der Aufgabenplaner ohnehin abbrechen sollen.
        """
        if lage.first_attempt_at is None:  # pragma: no cover -- 'running' ohne Beginn
            return []
        dauer = jetzt - lage.first_attempt_at.astimezone(jetzt.tzinfo)
        if dauer <= self._max_run_duration:
            return []
        stunden = dauer.total_seconds() / 3600
        return [
            f"Ein Lauf steht seit {stunden:.1f} Stunden auf 'running' und haelt "
            "damit die Sperre. Weitere Starts enden bei IN_PROGRESS, und die "
            "Ueberfaelligkeitsmeldung des Laufs kommt nicht hinaus -- sie laeuft "
            "innerhalb der Sperre."
        ]

    def _pruefe_sicherung(self, jetzt: datetime) -> list[str]:
        """Griff die Sicherung? Nur, wenn eine Ablage genannt wurde.

        Unabhaengig vom Handelstag: Gesichert wird taeglich, auch am
        Wochenende -- der Bestand ist dann zwar unveraendert, aber eine
        Sicherung, die samstags ausfaellt, faellt auch montags aus.
        """
        if self._latest_backup is None:
            return []
        stand = self._latest_backup()
        if stand is None:
            return ["In der Sicherungsablage liegt keine einzige Sicherung."]
        alter = jetzt - stand.astimezone(jetzt.tzinfo)
        if alter > self._max_backup_age:
            stunden = int(alter.total_seconds() // 3600)
            return [
                f"Die juengste Sicherung ist {stunden} Stunden alt "
                f"(Grenze {int(self._max_backup_age.total_seconds() // 3600)})."
            ]
        return []

    def _melde(self, befunde: list[str], jetzt: datetime) -> bool:
        """Stellt die Meldung zu. ``False``, wenn der Kanal nicht erreichbar war.

        Keine Kurse, keine Analyseergebnisse (ADR 0024) -- der Waechter
        kennt auch keine.
        """
        for befund in befunde:
            _logger.error("Waechter: %s", befund)
        if self._notifier is None:
            return False
        text = "\n\n".join(
            [f"Stand {jetzt.isoformat(timespec='minutes')}", *(f"- {b}" for b in befunde)]
        )
        try:
            self._notifier.send(MELDUNGSTITEL, text)
        except NotifierError as error:  # Systemgrenze: der Kanal
            _logger.error("Waechter konnte nicht melden: %s", error)
            return False
        return True
