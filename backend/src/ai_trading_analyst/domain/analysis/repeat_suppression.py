"""Wiederholsperre des Tageslaufs (ADR 0054).

Ein Symbol, dessen letzte volle Analyse juenger als das Sperrfenster ist,
wird vom Lauf komplett uebersprungen: keine Signalpruefung, keine Analyse,
keine Zeile in Ergebnis und Meldung. Anker ist die letzte volle Analyse --
ein unterdruecktes Wiederauftreten erzeugt keine neue Analysezeile und
verlaengert die Sperre deshalb nicht.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ai_trading_analyst.domain.scoring import Recommendation

RECOMMENDED_LEVELS = frozenset({Recommendation.STRONG_CANDIDATE, Recommendation.CANDIDATE})
"""Die nicht verdrahtete Auslöser-Variante "nur empfohlene Stufen sperren".

ADR 0054 hat sich fuer "jede volle Analyse sperrt" entschieden
(``recommendation_levels=None``); diese Konstante haelt den Wechsel als
Einzeiler offen, ohne einen Konfig-Schalter ohne Bedarf einzufuehren."""


@dataclass(frozen=True, slots=True)
class RepeatSuppressionParameters:
    """Sperrfenster des Tageslaufs.

    ``window_days``: Kalendertage; ``0`` schaltet die Sperre ab.
    ``recommendation_levels``: ``None`` sperrt nach jeder vollen Analyse
    (ADR 0054); eine Menge beschraenkt den Ausloeser auf diese Stufen.
    """

    window_days: int
    recommendation_levels: frozenset[Recommendation] | None = None


def suppression_cutoff(
    now: datetime, params: RepeatSuppressionParameters
) -> datetime | None:
    """Der Zeitpunkt, ab dem eine Analyse sperrt -- ``None`` bei Sperre aus.

    Strikte Grenze (ADR 0054): Gesperrt ist, was **juenger** als der Cutoff
    ist. Eine exakt ``window_days`` alte Analyse sperrt nicht mehr; die
    Abfrage vergleicht deshalb mit ``evaluated_at > cutoff``.
    """
    if params.window_days <= 0:
        return None
    return now - timedelta(days=params.window_days)
