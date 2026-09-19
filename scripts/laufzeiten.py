"""Wo die Zeit der letzten Tageslaeufe geblieben ist.

Rein lesend. Braucht **nichts Eingeschaltetes**: Die Zerlegung steht seit dem
ersten automatischen Lauf in der Datenbank, weil Meldung und Export hinter
``analysis_runs.completed_at`` liegen und der Dispatcher den ganzen Versuch
klammert.

    Backfill + Datengate  = analysis_runs.started_at   - dispatcher_runs.last_attempt_at
    Analyse (Phasen 1-3)  = analysis_runs.completed_at - analysis_runs.started_at
    Meldung + Export      = dispatcher_runs.finished_at - analysis_runs.completed_at

Die Zugangsdaten kommen aus derselben Quelle wie fuer die Anwendung
(``ATA_DATABASE_URL``, ersatzweise die ``.env`` im Projektwurzelverzeichnis) --
auf der Kommandozeile steht damit kein Passwort, und es braucht kein ``psql``
im Suchpfad.

Aufruf auf dem Server:

    backend\\.venv\\Scripts\\python.exe scripts\\laufzeiten.py
    backend\\.venv\\Scripts\\python.exe scripts\\laufzeiten.py --limit 60

Die **Streuung** ueber mehrere Wochen ist aussagekraeftiger als ein
Einzelwert: Die TWS antwortet nicht jeden Tag gleich schnell.
"""

from __future__ import annotations

import argparse
import statistics
import sys

from sqlalchemy import create_engine, text

from ai_trading_analyst.config.settings import MissingSecretError, Secrets

ABFRAGE = text(
    """
    SELECT d.session_date,
           a.number_of_stocks,
           a.candidates_found,
           extract(epoch from a.started_at   - d.last_attempt_at) AS backfill,
           extract(epoch from a.completed_at - a.started_at)      AS analyse,
           extract(epoch from d.finished_at  - a.completed_at)    AS rest,
           extract(epoch from d.finished_at  - d.last_attempt_at) AS gesamt
    FROM dispatcher_runs d
    JOIN analysis_runs a
      ON a.started_at BETWEEN d.last_attempt_at AND d.finished_at
    WHERE d.status = 'succeeded'
      AND a.completed_at IS NOT NULL
    ORDER BY d.session_date DESC
    LIMIT :limit
    """
)


def _minuten(sekunden: float | None) -> str:
    """Fehlt ein Wert, bleibt er fehlend -- kein Ersatzwert, keine Null."""
    if sekunden is None:
        return "     -"
    return f"{sekunden / 60:6.1f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=30, help="Wieviele Laeufe (Standard: 30)")
    args = parser.parse_args(argv)

    try:
        url = Secrets().require("database_url")
    except MissingSecretError as error:
        print(f"Konfiguration: {error}", file=sys.stderr)
        return 2

    engine = create_engine(url)
    with engine.connect() as verbindung:
        zeilen = verbindung.execute(ABFRAGE, {"limit": args.limit}).all()

    if not zeilen:
        print("Kein abgeschlossener Tageslauf gefunden.")
        return 0

    print(f"{'Tag':<12}{'Aktien':>7}{'Kand.':>7}"
          f"{'Backfill':>10}{'Analyse':>9}{'Rest':>8}{'Gesamt':>9}   (Minuten)")
    print("-" * 71)
    for zeile in zeilen:
        print(
            f"{zeile.session_date.isoformat():<12}"
            f"{zeile.number_of_stocks:>7}{zeile.candidates_found:>7}"
            f"{_minuten(zeile.backfill):>10}{_minuten(zeile.analyse):>9}"
            f"{_minuten(zeile.rest):>8}{_minuten(zeile.gesamt):>9}"
        )

    print()
    print(f"Median ueber {len(zeilen)} Laeufe (Minuten):")
    for name, feld in (
        ("Backfill + Datengate", "backfill"),
        ("Analyse (Phasen 1-3) ", "analyse"),
        ("Meldung + Export     ", "rest"),
        ("Gesamt               ", "gesamt"),
    ):
        werte = [getattr(z, feld) for z in zeilen if getattr(z, feld) is not None]
        if werte:
            print(f"  {name}  {statistics.median(werte) / 60:6.1f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
