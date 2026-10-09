"""Hat der Tageslauf in den letzten Wochen getan, was er soll?

Rein lesend, und ausdruecklich **ohne Protokolldatei**: Alles hier steht in
der Datenbank, auch rueckblickend fuer Tage, an denen niemand hingesehen hat.

Zwei Teile, weil es zwei verschiedene Fragen sind:

**Lief er?** Je Handelstag der Ausgang des Dispatchers, die Zahl der Versuche,
Beginn und Ende in Boersenzeit, die Dauer und die Zahl isolierter Fehler. Ein
Tag ohne Zeile ist dabei das lauteste Signal, das dieser Bericht kennt: Dann
ist nicht einmal ein Versuch bis zum Dispatcher gekommen.

**Kam heraus, was herauskommen soll?** Je Tag, wie viele Kandidaten einen
Optionsvorschlag bekamen -- und bei welchen nicht, getrennt nach den beiden
Gruenden, die verschiedene Dinge bedeuten:

* ``INSUFFICIENT_DATA`` heisst: Die Kette kam an, es blieb kein Vorschlag
  uebrig. Kein Verfallstermin im Zielfenster, kein Strike im Band, keine
  beidseitige Notierung. **Eine Aussage ueber den Markt, kein Ausfall.**
* **Leer** heisst: Die Optionsanalyse hat dieses Symbol nie zu Ende gebracht.
  Ein Ausfall der Quelle verlaesst diesen Weg als Fehler, den der Lauf je
  Aktie isoliert -- die Spalte bleibt dann leer. **Das ist der Ausfall.**

Die Unterscheidung ist der Grund, aus dem es dieses Skript gibt: "In manchen
Meldungen fehlen die Optionsdaten" laesst beides offen, und die beiden Lagen
haben nichts miteinander zu tun.

Die Zugangsdaten kommen aus derselben Quelle wie fuer die Anwendung
(``ATA_DATABASE_URL``, ersatzweise die ``.env`` im Projektwurzelverzeichnis).

Aufruf auf dem Server:

    backend\\.venv\\Scripts\\python.exe scripts\\betriebsbericht.py
    backend\\.venv\\Scripts\\python.exe scripts\\betriebsbericht.py --limit 30
"""

from __future__ import annotations

import argparse
import sys
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text

from ai_trading_analyst.config.loader import load_config
from ai_trading_analyst.config.settings import MissingSecretError, Secrets

LAEUFE = text(
    """
    SELECT d.session_date,
           d.status,
           d.attempts,
           d.last_attempt_at,
           d.finished_at,
           d.alert_sent_at,
           left(coalesce(d.last_error, ''), 60) AS fehlertext,
           a.id                AS lauf,
           a.status            AS lauf_status,
           a.number_of_stocks,
           a.candidates_found,
           (
             SELECT count(*) FROM analysis_run_errors e
             WHERE e.analysis_run_id = a.id
           )                   AS fehler
    FROM dispatcher_runs d
    LEFT JOIN analysis_runs a
      ON a.started_at BETWEEN d.last_attempt_at
                          AND coalesce(d.finished_at, d.last_attempt_at + interval '6 hours')
    ORDER BY d.session_date DESC
    LIMIT :limit
    """
)

OPTIONEN = text(
    """
    SELECT d.session_date,
           count(*)                                                       AS kandidaten,
           count(*) FILTER (WHERE s.options_status = 'COMPLETED')          AS mit_vorschlag,
           count(*) FILTER (WHERE s.options_status = 'INSUFFICIENT_DATA')  AS kein_treffer,
           count(*) FILTER (WHERE s.options_status IS NULL)                AS leer
    FROM dispatcher_runs d
    JOIN analysis_runs a
      ON a.started_at BETWEEN d.last_attempt_at
                          AND coalesce(d.finished_at, d.last_attempt_at + interval '6 hours')
    JOIN screening_results s
      ON s.analysis_run_id = a.id
    WHERE s.status = 'CANDIDATE'
    GROUP BY d.session_date
    ORDER BY d.session_date DESC
    LIMIT :limit
    """
)

GRUENDE = text(
    """
    SELECT left(coalesce(s.options_reason, '(ohne Angabe)'), 70) AS grund,
           count(*) AS anzahl
    FROM screening_results s
    WHERE s.status = 'CANDIDATE'
      AND s.options_status IS DISTINCT FROM 'COMPLETED'
      AND s.evaluated_at > now() - make_interval(days => :tage)
    GROUP BY grund
    ORDER BY anzahl DESC
    LIMIT 8
    """
)


def _uhrzeit(wert: object, zone: ZoneInfo) -> str:
    """Boersenzeit, weil der Lauf in Boersenzeit entschieden wird."""
    if wert is None:
        return "    -"
    return wert.astimezone(zone).strftime("%H:%M")  # type: ignore[attr-defined]


def _dauer(beginn: object, ende: object) -> str:
    if beginn is None or ende is None:
        return "     -"
    sekunden = (ende - beginn).total_seconds()  # type: ignore[operator]
    return f"{sekunden / 60:6.1f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=15, help="Wieviele Tage (Standard: 15)")
    args = parser.parse_args(argv)

    try:
        url = Secrets().require("database_url")
    except MissingSecretError as error:
        print(f"Konfiguration: {error}", file=sys.stderr)
        return 2

    zone = ZoneInfo(load_config().config.market.timezone)
    engine = create_engine(url)
    with engine.connect() as verbindung:
        laeufe = verbindung.execute(LAEUFE, {"limit": args.limit}).all()
        optionen = verbindung.execute(OPTIONEN, {"limit": args.limit}).all()
        gruende = verbindung.execute(GRUENDE, {"tage": args.limit * 2}).all()

    if not laeufe:
        print("Keine Zeile in dispatcher_runs -- es ist nie ein Versuch angekommen.")
        return 1

    print(f"Lief er?  (Zeiten in {zone.key})")
    print(
        f"{'Tag':<12}{'Ausgang':<12}{'Vers.':>6}{'Start':>7}{'Ende':>7}"
        f"{'Minuten':>9}{'Aktien':>8}{'Kand.':>7}{'Fehler':>8}  Hinweis"
    )
    print("-" * 94)
    offene = 0
    for z in laeufe:
        if z.status != "succeeded":
            offene += 1
        hinweis = z.fehlertext or ""
        if z.alert_sent_at is not None:
            hinweis = f"gemeldet; {hinweis}".rstrip("; ")
        print(
            f"{z.session_date.isoformat():<12}{z.status:<12}{z.attempts:>6}"
            f"{_uhrzeit(z.last_attempt_at, zone):>7}{_uhrzeit(z.finished_at, zone):>7}"
            f"{_dauer(z.last_attempt_at, z.finished_at):>9}"
            f"{z.number_of_stocks if z.number_of_stocks is not None else '-':>8}"
            f"{z.candidates_found if z.candidates_found is not None else '-':>7}"
            f"{z.fehler if z.fehler is not None else '-':>8}  {hinweis}"
        )

    print()
    print("Kam heraus, was herauskommen soll?")
    print(
        f"{'Tag':<12}{'Kand.':>7}{'mit Vorschlag':>15}"
        f"{'kein Treffer':>14}{'LEER':>7}"
    )
    print("-" * 55)
    leer_gesamt = 0
    for z in optionen:
        leer_gesamt += z.leer
        print(
            f"{z.session_date.isoformat():<12}{z.kandidaten:>7}"
            f"{z.mit_vorschlag:>15}{z.kein_treffer:>14}{z.leer:>7}"
        )

    if gruende:
        print()
        print("Warum kein Vorschlag entstand (haeufigste Gruende):")
        for z in gruende:
            print(f"  {z.anzahl:>5}x  {z.grund}")

    print()
    if offene:
        print(f"** {offene} von {len(laeufe)} Tagen sind nicht als 'succeeded' vermerkt.")
    if leer_gesamt:
        print(
            f"** {leer_gesamt} Kandidaten ohne Optionsstatus. Das ist der Ausfall, "
            "nicht 'kein Treffer'."
        )
    if not offene and not leer_gesamt:
        print("Keine Auffaelligkeit in diesem Zeitraum.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
