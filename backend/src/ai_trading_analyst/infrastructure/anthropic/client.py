"""Gemeinsamer Aufbau des Anthropic-Clients fuer beide Adapter.

Steht hier und nicht zweimal im Adapter, weil Research Agent und Technical
Agent denselben Fehler hatten: ``max_retries`` dem SDK-Standard ueberlassen
und ``timeout`` als Skalar gesetzt. Beides ist unauffaellig, solange nichts
lange dauert -- und beides wurde am Lauf vom 2026-08-24 zum Problem.
"""

from __future__ import annotations

import anthropic
import httpx

VERBINDUNGSAUFBAU_SEKUNDEN = 10.0
"""Der Verbindungsaufbau darf **nicht** so lange dauern wie die Antwort.

Ein Skalar-``timeout`` legt denselben Wert auf Verbindungsaufbau, Lesen,
Schreiben und Pool. Wer den Lesetimeout gross genug fuer eine echte
Recherche waehlt, macht damit unbemerkt auch den Verbindungsaufbau
minutenlang geduldig -- eine unerreichbare Gegenstelle blockiert dann einen
Platz im Agenten-Pool, statt sofort aufzugeben.
"""


TECHNISCHES_VERSAGEN: tuple[type[anthropic.APIError], ...] = (
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)
"""Fehlerarten, bei denen ein Ausweichmodell versucht werden darf (ADR 0037).

ADR 0021 laesst den Fallback ausdruecklich nur bei **technischem Versagen**
greifen -- „Timeout, Ratenlimit, Providerfehler", „nie als stille
Qualitaetsminderung ohne Kennzeichnung". Beide Adapter fingen bis dahin
``anthropic.APIError``, und darunter faellt auch ein 400 oder 404: Ein
vertippter Modellname im Profil fuehrte damit zum Ausweichmodell, statt
aufzufallen (ADR 0026, offener Punkt).

Die Trennlinie: Ein 400/404 sagt „die Anfrage ist falsch" -- sie wird mit
einem anderen Modell nicht richtiger. Ein Timeout, ein Ratenlimit oder ein
5xx sagt „die Anfrage war in Ordnung, der Dienst konnte gerade nicht".

``APIConnectionError`` schliesst ``APITimeoutError`` mit ein.

Bewusst eine **Aufzaehlung**, keine Regel ueber ``status_code``: Ein neuer
Fehlertyp im SDK landet damit ausserhalb und schlaegt sofort durch. Das ist
die sichere Richtung -- er faellt auf, statt still auszuweichen.
"""


def ist_technisches_versagen(error: anthropic.APIError) -> bool:
    return isinstance(error, TECHNISCHES_VERSAGEN)


def build_client(
    *,
    api_key: str,
    http_client: httpx.Client | None,
    read_timeout_seconds: float,
    max_retries: int,
) -> anthropic.Anthropic:
    """Baut den Client mit getrennten Timeouts und ausdruecklicher
    Wiederholungszahl.

    ``max_retries`` wird gesetzt und nicht dem SDK ueberlassen (Standard: 2).
    Der Unterschied ist teuer: Eine Anfrage, die in den Lesetimeout laeuft,
    erzeugt clientseitig **keine** Protokollzeile -- httpx protokolliert erst
    eine Antwort, und die kommt nie. Serverseitig sind die erzeugten Token
    trotzdem angefallen. Ein stiller Wiederholungslauf kostet also Geld, das
    in keiner Kostenschaetzung auftaucht, weil die Nutzungsdaten nur aus dem
    erfolgreichen Versuch stammen.

    Sichtbar wird das ueber die Dauer je Anfrage, die beide Adapter
    protokollieren: Eine Anfrage, die ungefaehr ein Vielfaches des
    Lesetimeouts gedauert hat, hat mit hoher Wahrscheinlichkeit wiederholt.
    """
    return anthropic.Anthropic(
        api_key=api_key,
        http_client=http_client,
        timeout=httpx.Timeout(
            read_timeout_seconds,
            connect=VERBINDUNGSAUFBAU_SEKUNDEN,
        ),
        max_retries=max_retries,
    )
