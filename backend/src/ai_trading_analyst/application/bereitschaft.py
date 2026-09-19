"""Wer auf wessen Daten wartet -- die Naht zwischen Backfill und Analyse.

Der Backfill holt die Bars eines Symbols und meldet es hier; die Analyse
wartet vor jeder Aktie, bis deren Bars liegen (ADR 0069). Mehr ist es nicht:
eine Menge gemeldeter Symbole, ein Schloss und eine Bedingung.

**Die Zusicherung, auf die es ankommt, ist die umgekehrte:** Niemand wartet
ewig. Endet der Backfill -- regulaer oder mit einem Fehler --, kehrt jeder
Wartende sofort zurueck, und die Analyse rechnet auf dem Bestand weiter, den
es gibt. Eine Wartestelle, die haengen bleiben kann, waere im Tageslauf
schlimmer als gar keine Verzahnung.
"""

from __future__ import annotations

import threading


class Bereitschaft:
    """Meldet und erwartet die Bereitschaft einzelner Symbole.

    Threadsicher fuer **einen** Melder und beliebig viele Wartende. Der
    Tageslauf hat genau einen Melder (den Backfill-Thread) und genau einen
    Wartenden (die Analyse im Hauptthread); die Klasse setzt das nicht
    voraus.
    """

    def __init__(self) -> None:
        self._bedingung = threading.Condition()
        self._bereit: set[str] = set()
        self._beendet = False

    def melde(self, symbol: str) -> None:
        """Die Bars dieses Symbols liegen im Bestand."""
        with self._bedingung:
            self._bereit.add(symbol)
            self._bedingung.notify_all()

    def beende(self) -> None:
        """Es kommt nichts mehr -- der Backfill ist durch oder gescheitert.

        Mehrfach aufrufbar. Jeder Wartende kehrt danach sofort zurueck, auch
        fuer ein Symbol, das nie gemeldet wurde: Ein Symbol, das der Backfill
        ausgelassen hat, ist kein Grund, den restlichen Lauf anzuhalten.
        """
        with self._bedingung:
            self._beendet = True
            self._bedingung.notify_all()

    def warte_auf(self, symbol: str) -> bool:
        """Wartet, bis das Symbol gemeldet ist oder nichts mehr kommt.

        Liefert, ob das Symbol tatsaechlich gemeldet wurde. ``False`` heisst
        nicht "Fehler", sondern "der Backfill hat es nicht mehr geschafft" --
        was die Analyse damit anfaengt, entscheidet sie selbst: Sie rechnet
        auf dem vorhandenen Bestand, und ob der aktuell genug ist, sagt die
        Pruefung der erwarteten Kerze.

        **Ohne Zeitgrenze, und das ist Absicht.** Eine Frist je Symbol waere
        eine zweite Stelle, an der ueber die Vollstaendigkeit eines Laufs
        entschieden wird; das entscheidet ``minimum_completion_ratio`` am
        Ende. Die Schranke nach oben ist, dass der Backfill endet -- und er
        endet, auch wenn er scheitert.
        """
        with self._bedingung:
            self._bedingung.wait_for(lambda: symbol in self._bereit or self._beendet)
            return symbol in self._bereit

    def warte_auf_ende(self) -> None:
        """Wartet, bis der Melder durch ist.

        Gebraucht **vor jedem Zugriff auf die TWS** (ADR 0069, Punkt 2): Die
        Optionsanalyse benutzt dieselbe Verbindung wie der Backfill, und die
        ist an den Thread gebunden, der sie aufgebaut hat. Ein Wechsel
        verwirft sie und baut sie neu auf -- bei abwechselnden Aufrufen also
        ein Verbindungsaufbau je Abruf.

        Die Analyse kann **vor** dem Backfill fertig sein: Sie ueberspringt
        die Titel der Wiederholsperre (ADR 0054), er fuehrt sie bewusst
        weiter nach. Ohne diese Stelle liefe die Optionsanalyse dann in einen
        noch laufenden Backfill hinein.
        """
        with self._bedingung:
            self._bedingung.wait_for(lambda: self._beendet)

    def warte_auf_anzahl(self, mindestens: int) -> int:
        """Wartet, bis so viele Symbole gemeldet sind -- oder nichts mehr kommt.

        Liefert, wieviele es geworden sind. Gebraucht fuer das Datengate
        (ADR 0069, Punkt 3): Es fragt, ob die Daten der Zielkerze ueberhaupt
        angekommen sind, und diese Frage laesst sich nach einer Handvoll
        Symbole genauso beantworten wie nach allen -- nur rund vierunddreissig
        Minuten frueher.
        """
        with self._bedingung:
            self._bedingung.wait_for(lambda: len(self._bereit) >= mindestens or self._beendet)
            return len(self._bereit)
