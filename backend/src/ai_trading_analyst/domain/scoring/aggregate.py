"""Umgewichtung und Mindestabdeckung -- eine Stelle fuer beide Scores (Doc 09).

Fehlende Daten werden sichtbar behandelt, nicht ersetzt:

1. Eine Komponente ist verfuegbar, wenn sie einen Teilwert hat.
2. Die Gewichte der verfuegbaren Komponenten werden auf 100 Prozent normiert.
3. Deckt das verfuegbare Gewicht weniger als die Mindestabdeckung ab,
   entsteht kein Score, sondern ``INSUFFICIENT_DATA``.
"""

from __future__ import annotations

from collections.abc import Sequence

from .values import (
    ComponentName,
    ScoreComponent,
    ScoreConfidence,
    ScoreKind,
    ScoreResult,
    ScoreStatus,
)

_GUTER_TEILWERT = 8.0
"""Ab hier zaehlt eine Komponente als positiver Faktor -- die oberen beiden
Stufen der Fuenftelskala (ADR 0045)."""

_SCHWACHER_TEILWERT = 4.0
"""Bis hier zaehlt sie als negativer Faktor -- die unteren beiden Stufen."""

_NACHKOMMASTELLEN = 1
"""Doc 10, Paragraph 6.11: kein Score darf Scheingenauigkeit vortaeuschen.
Eine Stelle ist, was die Ausgabe in Doc 09 zeigt -- und mehr, als die
Fuenftelskala hergibt."""


def aggregate(
    *,
    kind: ScoreKind,
    version: str,
    components: Sequence[ScoreComponent],
    minimum_coverage: float,
    normal_confidence_coverage: float,
    limiting_risks: Sequence[str] = (),
) -> ScoreResult:
    """Der Gesamtwert aus den Teilwerten -- oder ``INSUFFICIENT_DATA``."""
    if not components:
        raise ValueError(f"{kind}: ein Score ohne Komponenten ist keiner")
    gesamtgewicht = sum(k.weight for k in components)
    if gesamtgewicht <= 0:
        raise ValueError(f"{kind}: die Komponentengewichte summieren sich auf {gesamtgewicht}")

    verfuegbares_gewicht = sum(k.weight for k in components if k.available)
    abdeckung = verfuegbares_gewicht / gesamtgewicht

    if abdeckung < minimum_coverage:
        # Ohne Wert und ohne wirksame Gewichte: Es wurde nichts gerechnet,
        # und ein umgewichtetes Gewicht neben einem fehlenden Gesamtwert
        # saehe aus wie eine halbe Rechnung.
        return ScoreResult(
            kind=kind,
            status=ScoreStatus.INSUFFICIENT_DATA,
            version=version,
            components=tuple(components),
            coverage=abdeckung,
            confidence=ScoreConfidence.INSUFFICIENT_DATA,
            value=None,
            limiting_risks=(
                *limiting_risks,
                f"Datenabdeckung {abdeckung:.0%} unter der Untergrenze "
                f"{minimum_coverage:.0%} -- kein Score",
            ),
        )

    gewichtet = tuple(
        k.with_effective_weight(k.weight / verfuegbares_gewicht if k.available else 0.0)
        for k in components
    )
    gesamt = sum(k.effective_weight * (k.value or 0.0) for k in gewichtet)

    return ScoreResult(
        kind=kind,
        status=ScoreStatus.COMPLETED,
        version=version,
        components=gewichtet,
        coverage=abdeckung,
        confidence=(
            ScoreConfidence.NORMAL
            if abdeckung >= normal_confidence_coverage
            else ScoreConfidence.LOW_COVERAGE
        ),
        value=round(gesamt, _NACHKOMMASTELLEN),
        positive_factors=_faktoren(gewichtet, positiv=True),
        negative_factors=_faktoren(gewichtet, positiv=False),
        limiting_risks=tuple(limiting_risks),
    )


def _faktoren(components: Sequence[ScoreComponent], *, positiv: bool) -> tuple[str, ...]:
    """Die Begruendungsbausteine, direkt aus den Teilwerten abgeleitet.

    Doc 10, Paragraph 6.11 verlangt, dass die Begruendung mit den Teilwerten
    uebereinstimmt. Sie hier aus ihnen zu **rechnen** statt sie danebenzu-
    schreiben, macht ein Auseinanderlaufen unmoeglich -- und kein Satz
    entsteht dabei aus Freitext.
    """
    ausgewaehlt: list[tuple[ComponentName, float]] = [
        (k.name, k.value)
        for k in components
        if k.value is not None
        and (k.value >= _GUTER_TEILWERT if positiv else k.value <= _SCHWACHER_TEILWERT)
    ]
    ausgewaehlt.sort(key=lambda eintrag: eintrag[1], reverse=positiv)
    return tuple(f"{_BEZEICHNUNG[name]}: {wert:.1f}" for name, wert in ausgewaehlt)


_BEZEICHNUNG: dict[ComponentName, str] = {
    ComponentName.TECHNICAL_SIGNALS: "Technische Signale",
    ComponentName.SIGNAL_STATISTICS: "Historische Signalqualitaet",
    ComponentName.CHART_SETUP: "Chart-Setup",
    ComponentName.CHANCE_RISK: "Chance-Risiko-Verhaeltnis",
    ComponentName.NEWS_AND_EVENTS: "News- und Ereignislage",
    ComponentName.OPTIONS_ATTRACTIVENESS: "Optionsattraktivitaet",
    ComponentName.PROFITABILITY: "Profitabilitaet",
    ComponentName.GROWTH: "Wachstum",
    ComponentName.VALUATION: "Bewertung",
    ComponentName.BALANCE_SHEET_QUALITY: "Bilanzqualitaet",
}
"""Deutsche Bezeichnungen fuer die Begruendungsbausteine.

Muss jeden ``ComponentName`` fuehren -- ein Test haelt das fest, weil eine
fehlende Bezeichnung sonst erst im Bericht auffiele, und zwar als
``KeyError`` mitten im Zusammenstellen."""
