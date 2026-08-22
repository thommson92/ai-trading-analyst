# ADR 0026: Technical Agent — KI-Einordnung der deterministischen Chartauswertung

- Status: Angenommen
- Datum: 2026-08-22

## Kontext

[ADR 0025](0025-deterministische-chartauswertung-und-zonen.md) hat die
deterministische Hälfte des Technical Analysis Module gebaut: Trend, RSI,
Lage zu EMA5 und EMA20, ATR, jüngste Extrempunkte und mehrfach getestete
Preiszonen. Doc 10, Paragraph 6.8 verlangt dazu eine zweite, **getrennt zu
speichernde** Hälfte — die qualitative Interpretation. Sie nennt dafür genau
sechs Punkte:

> Stärke des Trends, Qualität des Breakouts, überkaufte oder überverkaufte
> Situation, mögliche Fehlsignalrisiken, Verhältnis von Chance und Risiko,
> Plausibilität eines Swing-Einstiegs.

Ein Ausgabeformat gibt Paragraph 6.8 nicht vor. Das kommt aus Paragraph 10:
Jede KI-Komponente muss gegen ein festes Schema validiert werden, Freitext
ohne strukturierte Felder genügt als interne Schnittstelle nicht.

Die Leitplanke steht in `CLAUDE.md` und in Doc 10, Paragraph 2.5: Ein
Sprachmodell darf erläutern, zusammenfassen und Risiken bewerten — es darf
keine Signalregel verändern, keine fehlenden Marktdaten erfinden und **keine
deterministische Berechnung ersetzen.** [ADR 0021](0021-ki-anbindung-anthropic-api.md)
führt den Technical Agent in seiner Risikotabelle bereits ausdrücklich so:

> | Technical Agent | nein — interpretiert nur bereits deterministisch
> berechnete Werte | Darf Signale nicht umdeuten |

## Entscheidung

### 1. Der Agent ordnet ein und rechnet nicht

Alle sechs Ausgaben sind **Enums**, die übrigen Felder Text. Das Modell
bekommt gar kein Feld, in das es eine berechnete Größe schreiben könnte. Das
ist die strukturelle Umsetzung von „Scores werden nie direkt aus LLM-Freitext
übernommen" — sie hängt nicht daran, dass ein Prompt befolgt wird.

### 2. Das Chance-Risiko-Verhältnis wird deterministisch berechnet

Doc 10 nennt es unter den sechs Einordnungen. Damit das Modell es einordnen
kann, ohne es zu erfinden, entsteht es vorher im Domain Layer: Weg bis zur
nächstgelegenen Unterstützung, Weg bis zum nächstgelegenen Widerstand, ihr
Verhältnis. Verfahrensversion steigt dadurch auf `technical-v3`.

Gerechnet wird dabei fast nichts: `PriceZone.distance_pct` misst bereits
gegen die dem Kurs zugewandte Kante, und die Zonen kommen nach Abstand
sortiert. Neu ist die Auswahl je Seite und eine Division.

Fehlt eine Seite, bleiben die Felder leer statt null. Ohne Zone unterhalb des
Kurses ist der Weg nach unten **unbekannt**, nicht kurz.

**Gespeichert statt beim Lesen abgeleitet.** Eine erst beim Lesen gebildete
Kennzahl verschöbe sich rückwirkend, sobald die Herleitung sich ändert — das
verbietet `CLAUDE.md` („Abgeschlossene Analysen werden nicht überschrieben"),
und es wäre genau das stille Uminterpretieren, gegen das ADR 0025 die
Verfahrensversion eingeführt hat. Außerdem lesen Optionsanalyse (Doc 10,
Paragraph 6.10: „Abstand zur nächsten Unterstützung") und Scoring
(Paragraph 6.11: „Chance-Risiko-Verhältnis") später aus persistierten
Ergebnissen; läge die Regel nur zur Laufzeit vor, müsste jedes Modul sie neu
implementieren.

### 3. Deterministisches Übersteuern statt Vertrauen

Ist `chance_risk_ratio` nicht berechenbar, setzt der Adapter
`risk_reward_rating` auf `NOT_ASSESSABLE` — **unabhängig davon, was das
Modell geantwortet hat**, mit einer Warnung im Log, wenn es etwas anderes
meldete.

Ohne diese Übersteuerung könnte eine Einstufung im Bericht stehen, zu der es
keine berechnete Grundlage gibt, und sie sähe dort aus wie eine gerechnete
Aussage. Der Adapter darf eine Modellaussage überschreiben; die Domain
rechnet nie auf Modellausgaben.

### 4. Das Modell sieht ausschließlich den Snapshot

Keine Rohkerzen, keine Signalliste, kein Earnings- oder Research-Ergebnis.
Was das Modell nicht sieht, kann es nicht nachrechnen und nicht mit einer
eigenen Zahl bestreiten. Die Modulentkopplung aus `CLAUDE.md` wird damit
nicht nur eingehalten, sondern ist an der Eingabe ablesbar.

`render_snapshot` ist deshalb eine öffentliche reine Funktion, und
`technical --show-prompt` gibt sie im Wortlaut aus — bewusst auch ohne
`--interpret`, damit sich ansehen lässt, was gesendet *würde*, ohne dass es
etwas kostet. Ohne diese Möglichkeit ließe sich die Zusage nur behaupten,
nicht prüfen.

Die Angriffsfläche für Prompt-Injection ist damit praktisch null: Es gibt
keine Werkzeuge, keinen Research-Text und keine Rohkerzen. Die einzigen
interpolierten Fremddaten sind Symbol und Börsenplatz aus der Watchlist, und
sie stehen außerhalb des `<chartauswertung>`-Blocks. Solange die Watchlist aus
`config/` stammt, ist das folgenlos; käme sie je aus einer fremden Quelle,
wäre das die Stelle, an der man ansetzen müsste.

### 5. Der Kurs *in* einer Zone wird ausdrücklich ausgewiesen

Die Auswahl der nächstgelegenen Zone je Seite überspringt `PRICE_INSIDE` —
eine Kante, in der man steht, ist kein Halt. Damit zeigen beide Wege auf die
Zonen **jenseits** dieser Zone. Die Modelleingabe sagt das ausdrücklich;
sonst läse sich ein günstiges Verhältnis harmlos, während der Kurs mitten in
einer starken Zone klemmt.

### 6. Die Auslegungsregel der Zonenstärke steht im Prompt

Aus ADR 0025: Die Stärke folgt der Zahl der **Wendepunkte**, nicht der
Berührungen. Eine Zone mit vielen Berührungen und einem Wendepunkt ist eine
Preisregion, die der Kurs durchläuft. Steht das nicht im Prompt, liest ein
Modell „12 Berührungen" als starke Zone, obwohl `WEAK` danebensteht.

### 7. Ein einziger Aufruf gegen ein striktes Schema

Abschluss über ein Client-Werkzeug mit `strict: true` und
`additionalProperties: false`, erzwungen über `tool_choice`. Der Konflikt aus
[ADR 0023](0023-research-agent-zitierarchitektur.md) — Zitatblöcke vertragen
sich nicht mit einem strikten Schema — entsteht hier nicht, weil es keine
Quellen gibt. Es braucht daher auch keine Zwei-Phasen-Architektur.

Pflichtfeld ist nur `status`: Bei `INSUFFICIENT_DATA` soll das Modell keine
Einstufungen erfinden müssen. Die Vollständigkeit bei `COMPLETED` erzwingt
der Adapter — ein `COMPLETED` ohne eine einzige Einstufung wird auf
`INSUFFICIENT_DATA` mit `reason="no_ratings"` herabgestuft.

Weitere Lehren aus ADR 0023 übernommen: eigene Typprüfung **zusätzlich** zum
Schema, kein Teilergebnis bei `stop_reason == "max_tokens"`, ausdrücklich
gesetztes `thinking`, eigenes `request_timeout_seconds`, und der Adapter
wirft ausschließlich seine Vertragsausnahme.

### 8. Kein Modellaufruf ohne Grundlage

Ist der Snapshot `INSUFFICIENT_DATA`, liefert der Adapter unmittelbar
`INSUFFICIENT_DATA` mit `reason="snapshot_insufficient"` — ohne Anfrage. Es
gäbe nichts einzuordnen, und der Aufruf kostete nur. Geprüft wird das im
Adapter (damit die Zusicherung am Vertrag hängt) und im Application Layer.

Kein eigener Status `SKIPPED`: Das wäre die vierte Variante von „nicht da".
`INSUFFICIENT_DATA` mit sprechendem `reason` folgt dem Muster von
`EarningsFilterResult.reason` und bleibt unterscheidbar.

### 9. Läuft für jeden Kandidaten, entkoppelt von allem anderen

Anders als der Research Agent, der `EARNINGS_CLEAR` voraussetzt, läuft die
Einordnung für **jeden** Kandidaten mit auswertbarer Chartlage. `CLAUDE.md`
entkoppelt die Analysemodule ohne Einschränkung, und gerade bei einem
Kandidaten mit nahem Earnings-Termin ist die Chartlage interessant.

Ein Ausfall ist nicht blockierend: Vertragsausnahme und roher Fehler ergeben
beide `UNAVAILABLE`, nie einen `StockProcessingError`. Der deterministische
Snapshot bleibt vollständig.

Ausgeführt wird in Phase 2 des Laufs, gemeinsam mit Research in einem Pool.
Getrennte Pools wären latenzgünstiger — eine hängende Recherche belegt bis zu
fünf Minuten einen der vier Plätze —, verdoppeln aber die
Nebenläufigkeitsstruktur. Bei der Größe der Watchlist ist ein gemeinsamer
Pool ausreichend; der Ausweg ist benannt, nicht gebaut.

### 10. Eigener Spaltensatz, nichts wird vermischt

`technical_ai_*` auf `screening_results`, getrennt von den
`technical_*`-Spalten. Kein Codepfad schreibt aus dem einen Satz in den
anderen; ein Integrationstest sichert zu, dass derselbe Snapshot mit und ohne
Einordnung identisch zurückkommt.

Sieben neue Enum-Typen in Postgres. Das ist Wartungsaufwand — jede künftige
Stufe braucht ein `ALTER TYPE ... ADD VALUE` —, aber das Repo verwendet
durchgängig Enum-Spalten, und die Datenbank fängt so einen Tippfehler ab,
statt ihn als Text durchzureichen.

### 11. Jedes Ergebnis führt mit, worauf es beruht

`model`, `prompt_version` und zusätzlich
`interpreted_analysis_version` — die Verfahrensversion der Chartauswertung,
die eingeordnet wurde. Doc 10, Paragraph 12 verlangt nachvollziehbar, welche
Daten verwendet wurden. Steigt das deterministische Verfahren später, bleibt
erkennbar, dass eine Einordnung die ältere Fassung gesehen hat, statt gegen
Zahlen gelesen zu werden, die sie nie kannte.

### 12. Der Port liegt bei den übrigen Ports

`TechnicalInterpreter` und `TechnicalInterpreterError` stehen in
`domain/analysis/ports.py`, neben `ResearchProvider`. ADR 0021 formuliert
„je Aufgabe ein Port in `domain/<aufgabe>/ports.py`"; die Umsetzung des
Research Agent hat es anders gemacht, und eine einzelne abweichende Datei
wäre für einen Leser verwirrender als die Abweichung vom ADR-Wortlaut. Die
Absicht von ADR 0021 — ein aufgabenspezifischer Port mit fachlichem Ein- und
Ausgang statt eines generischen LLM-Layers — ist eingehalten.

## Konsequenzen

### Positiv

- Die sechs Einordnungen aus Doc 10, Paragraph 6.8 liegen strukturiert und
  gegen ein Schema validiert vor — verwertbar für die Score-Komponente
  „Chart Setup" (Doc 09, 20 %) und für die Punkte 6 und 7 des Berichts
  (Doc 10, Paragraph 6.12).
- Das Chance-Risiko-Verhältnis steht als berechnete Zahl bereit, die
  Optionsanalyse und Scoring in Sprint 5 ohne eigene Herleitung übernehmen
  können.
- Die Trennung von Berechnung und Interpretation ist nicht nur eingehalten,
  sondern prüfbar: getrennte Spalten, getrennte Objekte, und mit
  `--show-prompt` die vollständige Modelleingabe im Wortlaut.
- Der Lauf bleibt vollständig, wenn das Modell ausfällt.

### Negativ / offen

- **Der Prompt ist noch nicht an echten Kursen erprobt.** ADR 0025 hat
  gezeigt, wie viel ein einziger realer Lauf aufdeckt — dort waren es zwei
  Konstruktionsfehler, die an synthetischen Reihen unsichtbar waren. Für die
  Einordnung steht dieser Lauf noch aus; die Prompt-Version `technical-agent-v1`
  ist entsprechend als erste Fassung zu lesen.
- **„Relevante Chartmuster" aus US-007 (Doc 04) werden nicht geliefert.** Es
  gibt keine deterministische Mustererkennung, und ein Modell, das aus einer
  Handvoll Zahlen Formationen benennt, würde genau das erfinden, was
  `CLAUDE.md` verbietet. Bewusste Zurückstellung: Entweder kommt eine
  deterministische Erkennung, oder die Anforderung entfällt.
- **Die Berichtsschema-Version** (Doc 10, Paragraph 8) existiert weiterhin
  nirgends im Code. Sie gehört zum Report Generator, nicht hierher — sie ist
  hier nur festgehalten, damit sie nicht übersehen wird.
- **Der Fallback greift auch bei einem 400.** `anthropic.APIError` umfasst
  Konfigurationsfehler; ein falsch geschriebener Modellname im Profil führt
  dann zum Ausweichmodell, statt aufzufallen. Bewusst wie beim Research
  Agent gehalten, damit beide Adapter sich gleich verhalten — sichtbar bleibt
  es über die Warnung im Log und über das an jedem Ergebnis gespeicherte
  Modell.
- **Beide Agenten teilen sich einen Thread-Pool.** Eine hängende Recherche
  kann bis zu fünf Minuten einen der vier Plätze belegen, während die kurzen
  Einordnungen warten. Bei der Größe der Watchlist unkritisch; getrennte
  Pools wären der Ausweg, falls die Kandidatenzahl wächst.
- **`min_touches` filtert weiterhin nach der falschen Größe** (ADR 0025,
  „Negativ / offen"). Für den Agenten ist das kein Hindernis: `strength` und
  `pivot_count` stehen an jeder Zone, und der Prompt weist ausdrücklich
  darauf hin, wie beide zu lesen sind.
