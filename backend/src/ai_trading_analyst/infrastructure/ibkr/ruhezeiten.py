"""Wann dieses Programm die TWS in Ruhe laesst (ADR 0078).

Auf demselben Server handelt eine zweite Anwendung ueber dieselbe
TWS-Instanz. Beide belegen Marktdatenleitungen des Kontos -- eine Ressource,
die das Konto hat und nicht die Verbindung. Um ihre Auftraege herum schweigt
dieses Programm deshalb.

**Die Zeitpunkte pflegt der Inhaber**, in Boersenzeit, in
``config/default.yaml``. Sie stehen nicht im Code: Sie haengen an seinem
Handelsplan und nicht an einer technischen Eigenschaft (dieselbe Begruendung
wie fuer die Uhrzeit der Aufgabenplanung, Doc 14).

**Gewartet wird, nicht uebersprungen.** Der Backfill muss jedes Symbol holen;
ein ausgelassenes waere ein Loch in der Kursreihe, und das waere teurer als
zehn Minuten Wartezeit. Die Kosten sind klein, weil die Fenster schmal sind
und die Arbeit danach weiterlaeuft: Bei 192 Symbolen und einem Fenster im
Backfill endet er zehn Minuten spaeter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class Ruhezeitpunkt:
    """Ein geplanter Handelszeitpunkt und die Tage, an denen er gilt.

    ``wochentage`` nach ISO: 1 ist Montag, 7 ist Sonntag. Ein Zeitpunkt ohne
    Tage gilt an keinem -- nicht an allen. Die stillschweigende Annahme
    "leer heisst jeden Tag" waere die gefaehrlichere: Sie machte aus einem
    Tippfehler in der Konfiguration eine taegliche Sperre.
    """

    zeit: time
    wochentage: frozenset[int]


@dataclass(frozen=True, slots=True)
class Ruhezeiten:
    """Die Fenster, in denen keine Anfrage an die TWS geht."""

    zeitpunkte: tuple[Ruhezeitpunkt, ...]
    radius: timedelta
    zeitzone: str

    @property
    def aktiv(self) -> bool:
        """Ohne Zeitpunkte oder ohne Radius gibt es keine Sperre."""
        return bool(self.zeitpunkte) and self.radius > timedelta()

    def fenster_am(self, tag: date) -> tuple[tuple[datetime, datetime], ...]:
        """Die Fenster dieses Boersentages, aufsteigend."""
        zone = ZoneInfo(self.zeitzone)
        gefunden = [
            (
                datetime.combine(tag, punkt.zeit, tzinfo=zone) - self.radius,
                datetime.combine(tag, punkt.zeit, tzinfo=zone) + self.radius,
            )
            for punkt in self.zeitpunkte
            if tag.isoweekday() in punkt.wochentage
        ]
        return tuple(sorted(gefunden))

    def ende_der_sperre(self, jetzt: datetime) -> datetime | None:
        """Bis wann geschwiegen wird -- oder ``None``, wenn gerade nicht.

        **Aneinandergrenzende Fenster verschmelzen.** Zwei Zeitpunkte, deren
        Fenster sich beruehren, sind eine Sperre und nicht zwei; wer nur das
        erste abwartete, liefe in das zweite hinein. Heute ueberlappt nichts
        -- 13:15 und 14:15 liegen eine Stunde auseinander --, aber die
        Zeitpunkte pflegt der Inhaber, und die Rechnung soll auch dann
        stimmen, wenn er zwei enger legt.
        """
        if not self.aktiv:
            return None
        lokal = jetzt.astimezone(ZoneInfo(self.zeitzone))
        # Auch der Vortag: Ein Fenster um Mitternacht reichte in diesen Tag
        # hinein, und die Zeitpunkte sind nicht auf den Nachmittag beschraenkt.
        fenster = self.fenster_am(lokal.date() - timedelta(days=1)) + self.fenster_am(
            lokal.date()
        )
        grenze = lokal
        ende: datetime | None = None
        for beginn, schluss in fenster:
            if beginn <= grenze < schluss:
                grenze = schluss
                ende = schluss
        return ende

    def naechstes_fenster(self, jetzt: datetime) -> tuple[datetime, datetime] | None:
        """Das naechste Fenster nach ``jetzt`` -- fuer das Protokoll.

        Gesucht wird in den naechsten acht Tagen: Ein Zeitpunkt, der nur
        freitags gilt, liegt sonst ausserhalb jedes kuerzeren Fensters.
        """
        if not self.aktiv:
            return None
        lokal = jetzt.astimezone(ZoneInfo(self.zeitzone))
        for versatz in range(8):
            for beginn, schluss in self.fenster_am(lokal.date() + timedelta(days=versatz)):
                if beginn > lokal:
                    return (beginn, schluss)
        return None  # pragma: no cover -- acht Tage decken jede Wochentagswahl ab
