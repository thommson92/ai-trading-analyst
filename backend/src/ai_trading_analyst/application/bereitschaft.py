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
        self._freigegeben: set[str] = set()
        self._geliefert: set[str] = set()
        self._beendet = False

    def melde(self, symbol: str, *, geliefert: bool = True) -> None:
        """Der Backfill ist mit diesem Symbol durch.

        **Freigeben und Liefern sind zweierlei.** Ein gescheiterter Abruf
        gibt das Symbol frei -- die Analyse soll nicht weiter darauf warten,
        es kommt nichts mehr --, aber er hat nichts geliefert. Ohne diese
        Unterscheidung zaehlte das Datengate Versuche statt Lieferungen: Bei
        nicht angemeldeter TWS scheitern alle 192 Symbole, alle 192 waeren
        gemeldet, und die Pruefung "ist ueberhaupt etwas angekommen" ginge
        durch.
        """
        with self._bedingung:
            self._freigegeben.add(symbol)
            if geliefert:
                self._geliefert.add(symbol)
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

        Liefert, ob fuer das Symbol tatsaechlich Bars ankamen. ``False``
        heisst nicht "Fehler", sondern "es kamen keine neuen Bars" --
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
            self._bedingung.wait_for(lambda: symbol in self._freigegeben or self._beendet)
            return symbol in self._geliefert

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
        """Wartet auf so viele **bearbeitete** Symbole und zaehlt die
        **gelieferten**.

        Die beiden Zahlen auseinanderzuhalten ist der ganze Sinn dieser
        Methode. Die Frage des Datengates lautet, ob die Daten der
        Zielkerze ueberhaupt angekommen sind (ADR 0069, Punkt 3) -- und sie
        laesst sich nach einer Handvoll Symbole genauso beantworten wie nach
        allen, nur rund vierunddreissig Minuten frueher.

        **Gewartet wird deshalb auf Bearbeitung, nicht auf Lieferung.** Bei
        nicht angemeldeter TWS liefert kein einziges Symbol; wer auf
        Lieferungen wartete, wartete bis zum Ende des Backfills -- also
        genau die halbe Stunde, die hier gespart werden soll. Gezaehlt wird
        dann, was davon wirklich ankam: bei 192 Fehlschlaegen null.
        """
        with self._bedingung:
            self._bedingung.wait_for(
                lambda: len(self._freigegeben) >= mindestens or self._beendet
            )
            return len(self._geliefert)
