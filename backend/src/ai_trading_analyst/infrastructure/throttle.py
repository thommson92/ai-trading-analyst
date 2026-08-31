"""Mindestabstand zwischen zwei Anfragen an denselben Anbieter.

Aus ``infrastructure.edgar.provider`` herausgezogen, als Finnhub dieselbe
Drossel brauchte: Der Messlauf ueber die Watchliste lief mit rund einer
Anfrage je Sekunde gegen Finnhubs Gratis-Grenze und verlor vier von 192
Symbolen an ``429 Too Many Requests`` (ADR 0046). Zwei Kopien derselben
zwanzig Zeilen haetten sich frueher oder spaeter unterschieden -- und zwar
still, weil eine zu grosszuegige Drossel nur unter Last auffaellt.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class Drossel:
    """Haelt den Mindestabstand zwischen zwei Anfragen ein.

    Threadsicher, obwohl die heutigen Aufrufer **sequentiell** holen (Phase 1
    von ``RunAnalysisUseCase``, ausserhalb der Agenten-Pools). Die Sperre
    kostet nichts und haelt die Zusicherung, wenn der Beschaffungspfad
    spaeter nebenlaeufig wird -- eine Drossel, die das nicht beruecksichtigt,
    laesst genau dann zu viele Anfragen durch, wenn es darauf ankommt.

    ``sleep`` ist einspeisbar, damit Tests den Abstand pruefen koennen, ohne
    ihn abzuwarten.
    """

    def __init__(self, max_per_second: float, sleep: Callable[[float], None] = time.sleep) -> None:
        if max_per_second <= 0:
            raise ValueError(f"max_requests_per_second muss positiv sein, war {max_per_second}")
        self._mindestabstand = 1.0 / max_per_second
        self._sleep = sleep
        self._sperre = threading.Lock()
        self._zuletzt = 0.0

    def warte(self) -> None:
        with self._sperre:
            jetzt = time.monotonic()
            rest = self._zuletzt + self._mindestabstand - jetzt
            if rest > 0:
                self._sleep(rest)
                jetzt += rest
            self._zuletzt = jetzt
