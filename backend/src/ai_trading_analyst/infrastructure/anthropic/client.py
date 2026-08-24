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
der vier Arbeiter, statt sofort aufzugeben.
"""


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
