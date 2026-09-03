# Architecture Decision Records

Jede Architekturentscheidung wird hier als eigenes Dokument festgehalten
(Doc 10, Paragraph 19).

## Format

Dateiname: `NNNN-kurzbeschreibung.md`, fortlaufend nummeriert.

Aufbau:

```markdown
# ADR NNNN: Titel

- Status: Vorgeschlagen | Angenommen | Abgeloest durch ADR-NNNN
- Datum: YYYY-MM-DD

## Kontext
Welches Problem steht an, welche Rahmenbedingungen gelten.

## Entscheidung
Was wird getan.

## Begruendung
Warum diese Option und nicht die Alternativen.

## Konsequenzen
Was folgt daraus, auch das Unangenehme.
```

Ein ADR wird nicht rueckwirkend geaendert. Aendert sich die Entscheidung,
entsteht ein neues ADR, das das alte ausdruecklich abloest.

## Uebersicht

| ADR | Titel | Status |
|---|---|---|
| [0001](0001-dokumentenhierarchie.md) | Doc 10 ist bei Widersprüchen maßgeblich | Angenommen |
| [0002](0002-branching-modell.md) | Branching-Modell main/dev mit Feature-Branches | Angenommen |
| [0003](0003-monorepo-und-schichtung.md) | Monorepo mit vier Schichten und erzwungenen Grenzen | Angenommen |
| [0004](0004-python-toolchain.md) | Python-Toolchain: pyproject, venv, ruff, mypy strict | Angenommen |
| [0005](0005-konfiguration-und-secrets.md) | Konfiguration in YAML, Geheimnisse aus der Umgebung | Angenommen |
| [0006](0006-kein-redis-im-mvp.md) | Kein Redis im MVP, Koordination über PostgreSQL | Angenommen (Nachtrag 2026-08-23: Stufe 2 durch ADR 0019 ersetzt) |
| [0007](0007-gate-g1-indikatorparameter.md) | Indikator-Parameter bleiben bis zur Freigabe leer | Abgelöst durch ADR 0010 |
| [0008](0008-reproduzierbare-installation.md) | Reproduzierbare Installation über Lock-Dateien | Angenommen (Erzeuger ersetzt durch ADR 0015) |
| [0009](0009-required-checks-nicht-konfigurierbar.md) | Required Status Checks derzeit nicht konfigurierbar (Plan-Limit) | Abgelöst durch [0031](0031-merge-schutz-aktiv.md) |
| [0010](0010-gate-g1-freigegeben.md) | Gate G1 fachlich freigegeben -- Indikator- und Signalparameter | Angenommen (Indikatorparameter gelten fort; Signal-B-Formel und 2-aus-3-Regel durch [0056](0056-kaufsignale-und-zusatzkriterien.md) abgelöst) |
| [0011](0011-ci-dispatch-unzuverlaessig.md) | GitHub-Actions-Workflow-Dispatch ist unzuverlaessig (Plattformseitig) | Angenommen (Nachtrag 2026-08-23: Verhalten besteht nicht mehr; der Merge-Schutz steht seit [0031](0031-merge-schutz-aktiv.md)) |
| [0012](0012-gate-g3-strang-a-no-go-non-display-nutzung.md) | Gate G3 Strang A -- NO_GO wegen Non-Display-Nutzungsverbots der TradingView-Nutzungsbedingungen | Angenommen |
| [0013](0013-interactive-brokers-kandidat-vorschlag.md) | Interactive Brokers als nächster Kandidat für Marktdaten -- Spike vorgeschlagen | Angenommen (Spike abgeschlossen, GO_WITH_LIMITATIONS; Schritt 4 freigegeben durch ADR 0014) |
| [0014](0014-ibkr-produktivintegration-freigegeben.md) | IBKR als produktive Marktdaten-Grundlage freigegeben -- technisch GO_WITH_LIMITATIONS, vertraglich GO | Angenommen |
| [0015](0015-plattformunabhaengige-lock-dateien.md) | Lock-Dateien plattformunabhängig erzeugen (uv statt pip-compile) | Angenommen |
| [0016](0016-ibkr-keine-quelle-fuer-research-daten.md) | IBKR ist keine Quelle für Research-Daten (RESC: NO_GO) | Angenommen |
| [0017](0017-finnhub-fuer-earnings-und-ratings.md) | Finnhub als Quelle für Earnings-Termine und Analystenratings | Angenommen; Nachtrag 2026-09-01: Kalenderfenster 120 Tage, Klassenaktien-Schreibweise übersetzt |
| [0018](0018-kein-windows-autologon.md) | Kein Windows-Autologon — manueller Start wird akzeptiert | Angenommen |
| [0019](0019-trading-day-dispatcher.md) | Trading-Day-Dispatcher — idempotenter Einzelstart statt Dauerprozess | Angenommen |
| [0020](0020-earnings-filter-status-und-handelstagskalender.md) | Earnings-Filter — reduziertes Statusmodell und Wochentagsnäherung für die Kerzenzählung | Angenommen; L2 und L3 durch [0030](0030-wochentagsnaeherung-bleibt.md) abgelöst |
| [0021](0021-ki-anbindung-anthropic-api.md) | KI-Anbindung — Anthropic API mit Modellprofilen je Analyseaufgabe | Angenommen |
| [0022](0022-research-agent-quellen.md) | Research Agent — Anthropic Web Search/Web Fetch, SEC EDGAR deterministisch für Fundamentaldaten | Angenommen (GO_WITH_LIMITATIONS) |
| [0023](0023-research-agent-zitierarchitektur.md) | Research Agent — Zitierarchitektur | Angenommen |
| [0024](0024-benachrichtigungskanal-telegram.md) | Benachrichtigungskanal — Telegram Bot API | Angenommen |
| [0025](0025-deterministische-chartauswertung-und-zonen.md) | Deterministische Chartauswertung — Swing-Pivots mit Clustering für Zonen | Angenommen |
| [0026](0026-technical-agent-ki-einordnung.md) | Technical Agent — KI-Einordnung der deterministischen Chartauswertung | Angenommen |
| [0027](0027-historientiefe-messen-vor-anspruch.md) | Historientiefe — messen, dann holen, was es gibt (E2, Weg a) | Angenommen (Messergebnis in ADR 0028) |
| [0028](0028-historientiefe-gemessen.md) | Historientiefe gemessen — mindestens 17,4 Jahre, `history_years: 5` bestätigt, Tiefen-Backfill beschlossen | Angenommen |
| [0029](0029-research-qualitaet.md) | Research-Qualität — Quellenrang neben der Lizenzklasse, deterministische Abdeckung, Zitatgrenze, Quellenalter roh | Angenommen (ersetzt Teile von ADR 0023) |
| [0030](0030-wochentagsnaeherung-bleibt.md) | Wochentagsnäherung im Earnings-Filter bleibt — der TWS-Kalender reicht nicht | Angenommen (entkräftet L3 aus ADR 0020) |
| [0031](0031-merge-schutz-aktiv.md) | Merge-Schutz auf `main` und `dev` — grüne CI erzwungen, Notausgang für den Inhaber | Angenommen (löst ADR 0009 ab) |
| [0032](0032-fundamentalanalyse-deterministisch.md) | Deterministische Fundamentalanalyse — Kennzahlen aus XBRL, Kurs als optionale Eingabe | Angenommen; Entscheidung 3 durch [0033](0033-zwoelfmonatswerte-statt-jahresabschluss.md) abgelöst |
| [0033](0033-zwoelfmonatswerte-statt-jahresabschluss.md) | Niveauzahlen und Bewertung auf die letzten zwölf Monate statt auf den Jahresabschluss | Angenommen (löst Entscheidung 3 aus ADR 0032 ab) |
| [0034](0034-fundamentaldaten-nach-dem-watchlist-lauf.md) | Aktualitätsschranke, Umsatz ohne Vetorecht, drei zugelassene Abweichler | Angenommen (ergänzt ADR 0032 und 0033; Nachtrag 2026-08-27 löst L1 aus ADR 0032, L3 aus ADR 0033 und L4 ein) |
| [0035](0035-fundamentaldaten-im-tageslauf.md) | Fundamentaldaten im Tageslauf — nur für Kandidaten, Kurs aus der letzten abgeschlossenen Kerze, je Lauf gespeichert | Angenommen |
| [0036](0036-nativer-windows-betrieb.md) | Nativer Windows-Betrieb ist das Deployment des MVP -- keine Container | Angenommen |
| [0037](0037-getrennte-agenten-pools-und-enges-ausweichmodell.md) | Getrennte Pools je Agent, Ausweichmodell nur bei technischem Versagen | Angenommen (loest R9 und E12 Punkt 1 des Audits vom 2026-08-23; stellt die Fuenf-Minuten-Angabe aus ADR 0026 richtig) |
| [0038](0038-backtest-im-tageslauf.md) | Backtest je Kandidat im Tageslauf, Earnings-Abweichung am Ergebnis gekennzeichnet | Angenommen (loest E1 und M4 des Audits vom 2026-08-23; E3 bleibt offen) |
| [0039](0039-report-generator.md) | Report Generator -- achtzehn Punkte, Luecken benannt, ohne Sprachmodell | Angenommen (fuehrt die Berichtsschema-Version ein, die Doc 10 Paragraph 8 fordert) |
| [0040](0040-inhalt-der-ergebnismeldung.md) | Die Ergebnismeldung nennt Symbole und Signalgruende -- keine Kurse | Angenommen (entscheidet E7 des Audits vom 2026-08-23; lockert ADR 0024 bewusst; Signaltypen-Punkt durch [0055](0055-put-vorschlag-und-signalzahl-in-der-ergebnismeldung.md) abgelöst) |
| [0041](0041-score-komponenten-und-gewichte.md) | Komponenten und Gewichte der beiden Scores | Angenommen (schliesst den Punkt, den ADR 0001 ausdruecklich offen liess; loest den Widerspruch zwischen Doc 09 und Doc 10 Paragraph 6.11) |
| [0042](0042-kein-historischer-earnings-filter.md) | Der Backtest bekommt keinen historischen Earnings-Filter | Angenommen (entscheidet E3 des Audits vom 2026-08-23 -- verworfen mit Begruendung, nicht vertagt) |
| [0043](0043-analystenempfehlungen-statt-kurszielen.md) | Analystenempfehlungen statt Kurszielen | Angenommen (entscheidet E11 des Audits vom 2026-08-23; baut nach, was ADR 0017 mitentschied) |
| [0044](0044-geheimnisse-an-der-log-senke-schwaerzen.md) | Geheimnisse werden an der Log-Senke geschwärzt | Angenommen (gemessener Befund: der Finnhub-Schlüssel stand in jeder erfolgreichen Anfragezeile) |
| [0045](0045-schwellen-der-score-teilwerte.md) | Schwellen der Score-Teilwerte | Angenommen (an 191 Titeln der Watchliste gemessen; erfüllt die Voraussetzung aus ADR 0041; Signal-Teilwerte durch [0056](0056-kaufsignale-und-zusatzkriterien.md) ersetzt) |
| [0046](0046-empfehlungsstufe-aus-beiden-scores.md) | Empfehlungsstufe aus beiden Scores | Angenommen (füllt Berichtspunkt 16 und die News-Komponente; erledigt den offenen Befund aus ADR 0045) |
| [0047](0047-scores-in-der-ergebnismeldung.md) | Scores in der Ergebnismeldung | Angenommen (lockert ADR 0040 in einem Punkt; entscheidet Finnhub L8; Zeilenformat und Kürzungstabelle durch [0055](0055-put-vorschlag-und-signalzahl-in-der-ergebnismeldung.md) abgelöst) |
| [0048](0048-optionsanalyse-im-tageslauf.md) | Cash Secured Puts aus der IBKR-Optionskette | Angenommen (füllt Berichtspunkt 13 und die sechste Score-Komponente; führt die dritte gerichtete Kopplung ein) |
| [0049](0049-dashboard-mvp-nur-lan.md) | Dashboard-MVP nur im eigenen Netz — keine Exposition, keine eigene Auth | Angenommen (entscheidet F12/E8, entsperrt Sprint 6; Exposition und Auth werden nach stabilem Betrieb neu bewertet) |
| [0050](0050-us-007-chartmuster-gestrichen.md) | Das US-007-Kriterium „relevante Chartmuster" ist gestrichen | Angenommen (entscheidet E13 des Audits vom 2026-08-23 — Streichung mit Vermerk statt stiller Löschung) |
| [0051](0051-research-im-dauerbetrieb-abgeschaltet.md) | Research Agent im Dauerbetrieb abgeschaltet — Provider-Wert `none` | Angenommen (Kostenentscheidung; löst nichts an ADR 0021/0023 ab — die Einzelprobe bleibt der Weg) |
| [0052](0052-dashboard-als-statischer-export.md) | Dashboard als statischer Export, ausgeliefert von der API | Angenommen (beantwortet die von ADR 0036 an den Dashboard-Sprint vertagte Container-Frage: weiterhin kein Container, kein Reverse Proxy) |
| [0053](0053-lese-api-kein-lauf-ueber-http.md) | Die Web-API ist lesend — kein Analyselauf über HTTP | Angenommen (entscheidet den MVP-Zuschnitt gegen Doc 10 §6.14; `POST /analysis-runs` entfällt, weil er auf dem Server einen Fixture-Lauf speichern würde) |
| [0054](0054-wiederholsperre-im-tageslauf.md) | Wiederholsperre im Tageslauf — sieben Tage je voll analysiertem Symbol | Angenommen (jeder Kandidaten-Treffer sperrt, auch WATCH; Ausschluss in der Application-Schicht, Bars laufen weiter) |
| [0055](0055-put-vorschlag-und-signalzahl-in-der-ergebnismeldung.md) | Put-Vorschlag und Signalzahl in der Ergebnismeldung | Angenommen (Blockformat mit Leerzeilen; löst ADR 0040 beim Signaltypen-Punkt und ADR 0047 bei „keine Rohdaten" ab) |
| [0056](0056-kaufsignale-und-zusatzkriterien.md) | Fünf Kriterien, drei müssen erfüllt sein — Signal B ohne Gap-up-Klausel | Angenommen (ersetzt die 2-aus-3-Regel und die Signal-B-Formel aus ADR 0010 sowie die Signal-Teilwerte aus ADR 0045; Cooldown-Aussage durch [0057](0057-torbedingungen-und-episoden.md) abgelöst) |
| [0057](0057-torbedingungen-und-episoden.md) | Torbedingungen an der Entscheidungskerze, Episoden statt Cooldown | Angenommen (Frische und Schlusskurs über EMA 20 als Filter ohne neue Signaltypen; Ereignis-Verkettung ersetzt den Cooldown; ATR-Stärkefilter geprüft und verworfen) |

## Offene Entscheidungen

Diese Punkte sind bewusst noch nicht entschieden und erhalten je ein eigenes
ADR, sobald die nötigen Informationen vorliegen:

- Anbindung an TradingView: Gate G2 mit `GO_WITH_LIMITATIONS` abgeschlossen
  (siehe `spikes/tradingview-cdp/REPORT.md`), Gate G3 mit **NO_GO**
  entschieden — siehe [ADR 0012](0012-gate-g3-strang-a-no-go-non-display-nutzung.md)
  und [docs/requirements/g3-entscheidungsvorlage.md](../requirements/g3-entscheidungsvorlage.md).
  TradingView ist damit als Datenquelle erledigt.
- Marktdaten-/Screening-Anbindung anstelle von TradingView — **entschieden.**
  Interactive Brokers ist über [ADR 0014](0014-ibkr-produktivintegration-freigegeben.md)
  als produktive Marktdaten-Grundlage freigegeben (technisch
  GO_WITH_LIMITATIONS, vertraglich GO). Schritt 4 aus
  [ADR 0013](0013-interactive-brokers-kandidat-vorschlag.md) ist damit
  abgeschlossen; die akzeptierten Einschränkungen, Annahmen und Restrisiken
  stehen in ADR 0014.
- Anbieter für historische Intraday-Kurse (F9) — durch IBKR beantwortet
  (ADR 0013, Spike-Frage 3/4: 195-Minuten-Aggregation und historische
  Abdeckung bis 2 Jahre live bestätigt).
- Kursziele (F9) — **entschieden: dauerhaft zurückgestellt.** Keine der zehn
  Score-Komponenten aus [ADR 0041](0041-score-komponenten-und-gewichte.md)
  braucht sie, und genau daran hatte das Audit die Entscheidung geknüpft. Der
  Finnhub-Endpunkt ist kostenpflichtig; welche Bezahlstufe ihn enthält, ist
  unbelegt. Stattdessen sind die **Analystenempfehlungen** nachgebaut, die
  ADR 0017 mitentschied und die nie jemand gebaut hatte — siehe
  [ADR 0043](0043-analystenempfehlungen-statt-kurszielen.md).
- Historische Berichtstermine für das Backtesting — **entschieden: werden
  nicht gebaut.** Ein `8-K`-Einreichungsdatum ist der *realisierte* Termin,
  nicht der zum Signalzeitpunkt bekannte; ein Filter darauf tauschte eine
  beschriebene Verzerrung gegen eine unbeschriebene und verstieße gegen die
  Look-ahead-Regel aus Doc 10 §6.6. Die Abweichung bleibt am Ergebnis
  gekennzeichnet (`BacktestResult.earnings_exclusion_applied`), Risiko R6
  bleibt **eingegrenzt, nicht geschlossen**. Der EDGAR-Weg bleibt vorgemerkt;
  die Entscheidung ist umkehrbar. Siehe
  [ADR 0042](0042-kein-historischer-earnings-filter.md).
- Anbieter für Optionsketten mit Greeks (F9) — durch IBKR beantwortet
  (ADR 0013, Spike-Frage 6: Optionsketten-Struktur und modellierte Greeks
  nach Aktivierung eines zusätzlichen Optionsmarktdaten-Abos live
  bestätigt).
- Benachrichtigungskanal (F10) — **entschieden.** Telegram Bot API, siehe
  [ADR 0024](0024-benachrichtigungskanal-telegram.md).
- Inhalt der Ergebnis-Benachrichtigung — **entschieden.** Symbole,
  Signaltypen, Fehlsignalrisiko als Stufe und der Hinweis auf einen
  unbekannten Berichtstermin; keine Kurse, keine Kennzahlen, kein Link.
  Siehe [ADR 0040](0040-inhalt-der-ergebnismeldung.md), das ADR 0024
  bewusst lockert -- und [ADR 0047](0047-scores-in-der-ergebnismeldung.md),
  das die dort offen gelassene Frage nach Punktzahlen entscheidet.
- KI-Anbieter und Modellprofile (F11) — **entschieden.** Anthropic API mit
  gestuften Modellprofilen je Analyseaufgabe, siehe
  [ADR 0021](0021-ki-anbindung-anthropic-api.md).
- Qualitative Interpretation der Chartauswertung — **entschieden.** Der
  Technical Agent ordnet ausschließlich deterministisch berechnete Werte
  ein, siehe [ADR 0026](0026-technical-agent-ki-einordnung.md).
- Handelstagskalender für den Earnings-Filter — **entschieden.** Die
  Wochentagsnäherung bleibt; IBKRs `liquidHours` reicht gemessen vier künftige
  Handelstage voraus, gebraucht werden elf. Siehe [ADR 0030](0030-wochentagsnaeherung-bleibt.md),
  das die Zusage L3 aus [ADR 0020](0020-earnings-filter-status-und-handelstagskalender.md)
  entkräftet.
- Prompt-Caching für den Research-Lauf — **entschieden: wird nicht gebaut.**
  Gemessen erfasste ein Cache-Breakpoint unter einem Prozent der Eingabe-Token;
  die Kosten entstehen in der serverseitigen Werkzeugschleife *innerhalb* einer
  Anfrage. Siehe [ADR 0023](0023-research-agent-zitierarchitektur.md), Nachtrag vom 2026-08-24.
- Merge-Schutz für `main` und `dev` — **entschieden: aktiv.** Das Repository
  ist öffentlich, damit ist die Sperre verfügbar; grüne CI ist erzwungen, der
  Pull Request ist Pflicht, der Inhaber behält einen Notausgang. Siehe
  [ADR 0031](0031-merge-schutz-aktiv.md), das
  [ADR 0009](0009-required-checks-nicht-konfigurierbar.md) ablöst.
- Vergleichsgruppe für die Fundamentalanalyse („Bewertung gegenüber
  Wettbewerbern", Doc 10 Paragraph 6.9) — **offen.** Nicht aus XBRL ableitbar;
  [ADR 0032](0032-fundamentalanalyse-deterministisch.md) weist den Bereich als
  fehlend aus, statt ihn zu schätzen.
- Stichtagsbindung von Kennzahlen aus zwei Bilanzstichtagen — **offen.**
  Verschuldungsgrad und Liquiditätsgrad stehen auf zwei Werten desselben
  Bilanzstichtags, müssen aber mit dem Stichtag des Umsatzes zusammenfallen.
  Bei Kalenderjahr-Bilanzierern fällt der Liquiditätsgrad dadurch aus
  (gemessen an Coca-Cola). Siehe [ADR 0034](0034-fundamentaldaten-nach-dem-watchlist-lauf.md),
  Einschränkung L3.
- Deployment-Zielbild -- **entschieden.** Der native Betrieb auf dem
  Windows-Server ist das Deployment des MVP; Containerisierung wird zum
  Dashboard-Sprint neu bewertet. Siehe
  [ADR 0036](0036-nativer-windows-betrieb.md), das Doc 13 und Doc 10
  Paragraph 14 abloest. **Die vertagte Neubewertung ist erfolgt:** Das
  Dashboard wird als statischer Export von der API mit ausgeliefert — kein
  Container, kein Reverse Proxy, siehe
  [ADR 0052](0052-dashboard-als-statischer-export.md).
- Komponenten und Gewichte der beiden Scores — **entschieden.** Swing: die
  sechs Komponenten aus Doc 10 §6.11, mit Gewichten. Investment: vier statt
  acht — nur das, was deterministisch gerechnet wird. Fehlende Komponenten
  werden umgewichtet; unterhalb von 60 % Abdeckung entsteht kein Score,
  sondern `INSUFFICIENT_DATA`. Siehe
  [ADR 0041](0041-score-komponenten-und-gewichte.md) und den Nachtrag an
  [ADR 0001](0001-dokumentenhierarchie.md). **Die Schwellen** (Kennzahl →
  Teilwert 0–10) sind inzwischen ebenfalls entschieden: an 191 Titeln der
  Watchliste gemessen, siehe
  [ADR 0045](0045-schwellen-der-score-teilwerte.md). Damit rechnen beide
  Scores.
- Ableitung der Empfehlungsstufe aus beiden Scores (Berichtspunkt 16) —
  **entschieden.** Der Swing-Score führt, der Investment-Score korrigiert um
  höchstens eine Stufe, begrenzende Risiken decken danach. Dieselbe
  Entscheidung liefert die Komponente „News- und Ereignislage" nach; der
  Swing-Score rechnet damit auf 90 % Abdeckung. Siehe
  [ADR 0046](0046-empfehlungsstufe-aus-beiden-scores.md).
- Punktzahlen in der Ergebnismeldung — **entschieden.** Beide Scores und die
  Empfehlungsstufe gehen hinaus, sortiert nach Swing-Score. Siehe
  [ADR 0047](0047-scores-in-der-ergebnismeldung.md), das ADR 0040 in genau
  diesem Punkt ablöst und Finnhubs Einschränkung L8 dazu entscheidet.
- Optionsstrategien im Tageslauf (F9) — **entschieden.** Cash Secured Puts
  aus der IBKR-Optionskette, ein Verfallstermin je Kandidat, drei Vorschläge
  nach annualisierter Prämienrendite; der Berichtstermin schließt Verfälle
  danach aus. Siehe [ADR 0048](0048-optionsanalyse-im-tageslauf.md), das
  zugleich die Schwellen der Optionsattraktivität nach dem Muster von
  [ADR 0045](0045-schwellen-der-score-teilwerte.md) misst.
- Externer Zugriff auf das Dashboard (F12) — **entschieden.** Das MVP ist
  ausschließlich aus dem eigenen Netz (LAN/VPN) erreichbar, ohne Exposition
  und ohne eigene Authentifizierung; beides wird nach stabilem Betrieb neu
  bewertet. Siehe [ADR 0049](0049-dashboard-mvp-nur-lan.md). Damit ist die
  letzte Sprint-blockierende Frage dieser Liste beantwortet.
