"""Der Datenbaum, den das Dashboard ausserhalb des Servers anzeigt (ADR 0060).

Kein zweiter Zuschnitt der Zahlen: Die Dateien enthalten die Antworten der
lesenden Endpunkte, gebaut von ``presentation.api.views`` -- demselben Code,
den auch die API benutzt.
"""

from .snapshot import (
    ENDSTATUS,
    MANIFEST_PFAD,
    SNAPSHOT_FORMAT,
    BekannteDatei,
    Exportdatei,
    Exportquellen,
    dateisicherer_name,
    iter_snapshot,
)

__all__ = [
    "ENDSTATUS",
    "MANIFEST_PFAD",
    "SNAPSHOT_FORMAT",
    "BekannteDatei",
    "Exportdatei",
    "Exportquellen",
    "dateisicherer_name",
    "iter_snapshot",
]
