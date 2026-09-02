# ADR 0017: Finnhub als Quelle für Earnings-Termine und Analystenratings

- Status: Angenommen
- Datum: 2026-08-13

## Kontext

Filter F9 braucht zwei Dinge, die IBKR nicht liefern darf: **künftige
Berichtstermine** und **Analystenratings**. Nach
[ADR 0016](0016-ibkr-keine-quelle-fuer-research-daten.md) ist IBKR als
Research-Quelle ausgeschieden, damit fehlten beide.

Entscheidend für die Auswahl war eine Größenordnung, die zunächst falsch
angesetzt war: **Der Earnings-Filter greift nicht auf der ganzen Watchlist,
sondern nur auf den Kandidaten eines Tages — in der Regel 10 bis 20 Titel.**
Damit ist das Anfragekontingent bei keinem Anbieter die bindende Grenze, und
die Auswahl entscheidet sich an Lizenz, Endpunktverfügbarkeit und
Datenqualität.

Die vollständige Bewertung mit allen Belegen steht in
[`docs/requirements/earnings-anbieter-evaluation.md`](../requirements/earnings-anbieter-evaluation.md).

## Entscheidung

**Finnhub wird in seiner kostenlosen Stufe die Quelle für Earnings-Termine
und Analystenempfehlungen.**

Drei Abgrenzungen gehören zur Entscheidung:

- **Ohne Kursziele.** Der Endpunkt ist kostenpflichtig (HTTP 403). F9 läuft
  vorerst ohne diese Kennzahl; sie ist in einer späteren Ausbaustufe
  nachrüstbar.
- **Ohne SEC EDGAR.** Historische Berichtstermine für das Backtesting sind
  über EDGAR lizenzfrei zu bekommen (Einreichungsdatum des `8-K` mit Item
  2.02). Das ist zurückgestellt, aber als Weg vorgemerkt.
- **Kein zweiter Anbieter.** Weder für Kursziele noch für die Bestätigung
  von Terminen.

## Begründung

Von den geprüften Anbietern ist Finnhub der einzige, dessen **Gratis-Stufe
den Earnings-Kalender überhaupt enthält**. Bei Financial Modeling Prep,
Alpha Vantage und EODHD ist der Endpunkt kostenpflichtig — unabhängig vom
Anfragekontingent.

Die Lizenzlage ist prüfbar und trägt: Die Bedingungen sind öffentlich,
erlauben private Nutzung ausdrücklich und setzen abgeleitete Ergebnisse
voraus. Das unterscheidet den Fall von den beiden Absagen — TradingView
verbot die nicht-anzeigende Nutzung ausdrücklich (ADR 0012), bei IBKR RESC
war überhaupt kein Vertragsdokument auffindbar (ADR 0016). Der Maßstab
„Schweigen ist keine Erlaubnis" bleibt damit unangetastet; hier liegt der
Vertrag vor und gewährt, worauf es ankommt.

Die Abdeckung der eigenen Watchlist liegt bei 97 % (186 von 192), gemessen
über vier Monate — ein Zeitraum, in dem jeder Quartalsberichterstatter
mindestens einmal auftauchen muss.

## Akzeptierte Einschränkungen

Vom Projektinhaber ausdrücklich übernommen, nicht als offene Punkte:

| # | Einschränkung | Folge für die Implementierung |
|---|---|---|
| L1 | **Keine Kennzeichnung bestätigt/geschätzt.** Ein Feld dafür existiert nicht, und die Tageszeit taugt nicht als Ersatz — sie ist ein Merkmal der Abdeckung, nicht der Bestätigung (64 % bei großen Titeln über alle Vorlaufwochen, 20 % bei den übrigen) | **Jeder Termin zählt**, auch der geschätzte. Eine verpasste Gelegenheit kostet weniger als eine Position in eine Ergebnismeldung hinein. Die Unsicherheit steht am Ergebnis |
| L2 | **Tageszeit (`bmo`/`amc`) nur bei 64 % der eigenen Titel** | **Nice-to-have, kein Pflichtfeld.** Der Filter macht ihr Fehlen weder zum Ausschlusskriterium noch nimmt er eine an. Liegt sie vor, verfeinert sie die Zuordnung zur Kerze; fehlt sie, gilt der ganze Handelstag als betroffen |
| L3 | **Abdeckung 97 %.** Ohne Termin blieben `BDX`, `BRK.B`, `MGA`, `NVO`, `SPCX`, `SWKS` — erkennbar Schreibweisen, ausländische Emittenten, eine Neuemission und abweichende Geschäftsjahre | **Ein fehlender Termin ist nicht „keine Earnings in Sicht".** Er ist fehlende Information, senkt Datenabdeckung und Konfidenz und wird als solche ausgewiesen (Doc 10) |
| L4 | **1500 Treffer je Anfrage, Kürzung am Anfang des Zeitraums, ohne jeden Hinweis in der Antwort** | Die Anbindung muss die Kürzung **erkennen und den Zeitraum teilen**, bis die Antwort vollständig ist. Eine feste Fenstergröße genügt nicht: 30 Tage reichen im September, Ende Oktober nicht |
| L5 | **Keine Kursziele** | Das Feld gilt als nicht verfügbar. Kein Ersatzwert, keine Schätzung |
| L6 | **Löschpflicht bei Ende des Bezugs** — „All data must be deleted should your subscription to that data ends" | Derzeit **nicht ausgelöst**: Die Gratis-Stufe läuft nicht ab. Auslösen würde sie das Ende des Bezugs überhaupt — Kontoschließung, Sperrung des Schlüssels, Einstellung der Gratis-Stufe. Tritt das ein, ist zu entscheiden, was mit gespeicherten Terminen geschieht; bis dahin besteht keine Löschpflicht |
| L7 | **Persönlicher Plan setzt Nicht-Professionalität voraus** — keine geschäftliche Nutzung, keine Absetzung als Betriebsausgabe | Gilt als zugesichert. Ändert sich der Status, ist die Entscheidung neu zu treffen |
| L8 | **Weitergabe an Dritte ist untersagt**, einschließlich abgeleiteter Ergebnisse | **F12 (externer Zugriff auf das Dashboard) ist davon berührt** und darf ohne schriftliche Zustimmung keine Finnhub-Daten oder daraus abgeleiteten Ergebnisse zeigen |
| L9 | **Nur künftige Termine.** Historische Berichtstermine für das Backtesting deckt der Kalender nicht ab | Der Earnings-Filter im Backtesting bleibt vorerst ohne Datengrundlage. EDGAR ist der vorgemerkte Weg |

## Konsequenzen

- Der Zugangsschlüssel ist ein Geheimnis und kommt ausschließlich aus der
  Umgebungsvariablen `ATA_FINNHUB_API_KEY` — nicht in den Code, nicht in
  `config/default.yaml`, nicht als Kommandozeilenargument (ADR 0005).
- Finnhub wird ein **Infrastructure-Adapter hinter einem Domain-Protokoll**,
  wie IBKR bei den Marktdaten. Der Domain Layer kennt keinen Anbieter.
- Ein Ausfall der Quelle ist ein **normaler Betriebszustand**, kein Abbruch:
  Fällt der Abruf aus, bleibt der Earnings-Filter ohne Grundlage und das
  Ergebnis wird entsprechend gekennzeichnet. Die technische Analyse läuft
  unabhängig weiter (Doc 10: Analysemodule sind entkoppelt).
- Die Empfehlungen liefern **vier Monatsstände je Symbol**. Die Veränderung
  der Analystenmeinung über die Zeit ist damit ohne Zusatzaufwand verfügbar
  und kann später in das Scoring eingehen.
- Ändert sich die Lizenzlage, entfällt die Gratis-Stufe oder wird ein
  Kursziel benötigt, ist das ein **neues ADR** — dieses wird nicht
  rückwirkend geändert.

## Nachtrag vom 2026-09-01: Kalenderfenster 120 Tage, Klassenaktien übersetzt

Der erste scharfe Verbundlauf (2026-09-01) zeigte bei rund zwei Dritteln der
Kandidaten „Earnings-Termin unbekannt". Ursache war nicht der Anbieter,
sondern das produktive Abfragefenster von 30 Kalendertagen je Symbol:
Quartalsberichte kommen nur ~alle 90 Tage, also lag zu jedem Zeitpunkt nur
bei rund einem Drittel der Titel ein Termin im Fenster. Die 97 % Abdeckung
dieses ADRs waren dagegen über ein **Vier-Monats-Fenster** gemessen.

Zwei Änderungen:

- **`earnings_filter.lookahead_calendar_days` steigt von 30 auf 120.** Der
  Termin hat seit ADR 0046/0048 drei Verbraucher, und nur der erste kam mit
  30 Tagen aus: das Ausschlussfenster (10 Handelstage), die Kennzeichnung
  `earnings_within_term` der Optionsanalyse (Verfälle bis 60 Tage voraus)
  und der Empfehlungsdeckel `cap_earnings_unknown` — mit 30 Tagen blieb die
  Empfehlung jedes Titels mit fernerem Termin dauerhaft gedeckelt. Ein
  größeres Fenster ist ein reiner Query-Parameter und kostet keine
  zusätzliche Anfrage; die Plausibilitätsschranke von 50 Einträgen je Symbol
  bleibt auch bei 120 Tagen weit entfernt (maximal ~2 Termine). Die
  1500-Treffer-Kürzung aus L4 betrifft nur kalenderweite Anfragen ohne
  `symbol`-Parameter — je Symbol bleibt sie unerreichbar.
- **Klassenaktien werden in Finnhub-Schreibweise übersetzt** (`BRK B` →
  `BRK.B`, `infrastructure/finnhub/symbols.py`, beide Endpunkte). Damit ist
  der Schreibweisen-Anteil von L3 eingelöst; ausländische Emittenten,
  Neuemissionen und abweichende Geschäftsjahre (`NVO`, `MGA`, `SPCX`)
  bleiben als echte Abdeckungslücken bestehen und werden weiterhin als
  fehlende Information ausgewiesen.

Außerdem loggt der `provider_error`-Pfad des Earnings-Filters seither eine
Warnung mit Symbol und Ursache — er war der einzige Ausfallpfad ohne
Logzeile, ein 429 war im Log nicht von `no_coverage` zu unterscheiden.
