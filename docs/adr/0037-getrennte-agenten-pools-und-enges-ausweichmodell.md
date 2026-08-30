# ADR 0037: Getrennte Pools je Agent, Ausweichmodell nur bei technischem Versagen

- Status: Angenommen
- Datum: 2026-08-30

## Kontext

Zwei Restposten aus dem Repository-Audit vom 2026-08-23, die sich beide auf
die KI-Aufrufe im Tageslauf beziehen und deshalb zusammen entschieden werden.

**Risiko R9 — ein Pool für zwei Agenten.** `RunAnalysisUseCase` führte die
Modellaufrufe beider Agenten über einen `ThreadPoolExecutor` mit vier
Plätzen. Die beiden Aufrufe sind aber grundverschieden:

| | Research Agent | Technical Agent |
|---|---|---|
| Dauer | ~15 Minuten (Messung 2026-08-24) | Sekunden |
| Lesetimeout | 900 s | 60 s |
| Kosten je Titel | ~0,58 USD | ~0,005 USD |
| Serverseitige Werkzeugschleife | ja | nein |

Eine hängende Recherche belegte damit bis zu 900 Sekunden einen der vier
Plätze, während die kurzen Einordnungen warteten. ADR 0026 hat den Ausweg
benannt, aber nicht gebaut — und nennt dort noch „fünf Minuten", weil er vor
der Anhebung des Lesetimeouts auf 900 s durch ADR 0023 geschrieben wurde.

**Entscheidung E12 ① — `fallback_model`.** ADR 0021 sieht je Modellprofil ein
Ausweichmodell vor. Der Zweig ist in beiden Adaptern gebaut und getestet, aber
`fallback_model` ist in `config/default.yaml` für alle vier Profile nicht
gesetzt. Er läuft also nie; der einzige jemals genommene Pfad ist
`if self._fallback_model is None: raise`.

Dazu kommt ein Befund aus ADR 0026: Der Fallback fängt `anthropic.APIError`,
und darunter fallen auch Konfigurationsfehler. Ein vertippter Modellname im
Profil führte damit zum Ausweichmodell, statt aufzufallen. Das widerspricht
dem Wortlaut von ADR 0021 — „greift nur bei technischem Versagen (Timeout,
Ratenlimit, Providerfehler) — nie als stille Qualitätsminderung ohne
Kennzeichnung".

## Entscheidung

### 1. Je Agent ein eigener Pool

Statt einer Modulkonstante `_MAX_CONCURRENT_AGENT_CALLS = 4` gibt es zwei
konfigurierbare Werte in den bereits vorhandenen Abschnitten:

| Schlüssel | Wert | Grund |
|---|---|---|
| `research.max_concurrent_calls` | 2 | teuer und langsam; mehr Nebenläufigkeit verkürzt den einzelnen Aufruf nicht, sie erhöht nur, wie viele teure Gespräche gleichzeitig offen sind |
| `technical_agent.max_concurrent_calls` | 4 | billig und kurz |

Beide Pools sind gleichzeitig offen, während `as_completed` über die Aufträge
beider läuft. Zugewiesen wird weiterhin ausschließlich im Hauptthread.

### 2. Ausweichmodelle werden gesetzt — und greifen enger

`fallback_model` wird je Profil belegt. Zugleich wird die Auslöserbedingung
von `anthropic.APIError` auf eine **ausdrückliche Liste technischer Fehler**
verengt: Zeitüberschreitung, Verbindungsabbruch, Ratenlimit und
Serverfehler (5xx). Alles andere — insbesondere 400 und 404 — schlägt sofort
durch.

## Begründung

**Zu 1.** Ein gemeinsamer Pool ist einfacher, aber die Annahme dahinter
stimmt nicht: Er unterstellt vergleichbare Aufrufe. Tatsächlich unterscheiden
sich Dauer und Kosten um mehr als zwei Größenordnungen. Ein Platz ist für die
Recherche eine teure Ressource und für die Einordnung eine billige; ein
gemeinsamer Zähler kann nicht beides richtig bemessen.

Die Zahlen fallen dabei auseinander, nicht zusammen: Für die Recherche ist
weniger Nebenläufigkeit besser, für die Einordnung mehr. Ein einzelner Regler
hätte für beide den falschen Wert.

**Zu 2.** Ein Ausweichmodell, das nie greift, ist keine Absicherung, sondern
toter Code mit einem beruhigenden Namen. Umgekehrt ist ein Ausweichmodell,
das bei einem Tippfehler im Profil anspringt, schlimmer als keins: Der Lauf
gelingt, das Ergebnis trägt ein anderes Modell, und niemand merkt, dass das
konfigurierte nie erreicht wurde. Genau das meint ADR 0021 mit „nie als
stille Qualitätsminderung".

Die Trennlinie ist sauber zu ziehen. Ein 400 oder 404 sagt: *Die Anfrage ist
falsch.* Sie wird mit einem anderen Modell nicht richtiger. Ein Timeout, ein
Ratenlimit oder ein 5xx sagt: *Die Anfrage war in Ordnung, der Dienst konnte
gerade nicht.* Dort ist ein zweiter Versuch mit einem anderen Modell sinnvoll.

## Konsequenzen

**Positiv**

- Eine hängende Recherche hält die Einordnungen nicht mehr auf. Das ist
  zugesichert und durch eine Mutation belegt: Wird wieder ein gemeinsamer Pool
  daraus, kommen von fünf Einordnungen nur drei durch.
- Die Nebenläufigkeit steht in der Konfiguration statt im Code. Wer sie
  ändern will, braucht kein Deployment.
- Der Fallback wird zum ersten Mal wirksam — und ein falsch geschriebener
  Modellname fällt sofort auf, statt still ein anderes Modell zu verwenden.
- R9 und E12 ① aus dem Audit vom 2026-08-23 sind erledigt.

**Negativ und offen**

- **Zwei Pools statt einem** sind mehr Struktur. Der Aufwand ist einmalig und
  wird durch die Zusicherung gedeckt; wer die Pools wieder zusammenlegt,
  bricht einen Test, der sagt, warum.
- **Die Obergrenze ist jetzt in Summe höher** (2 + 4 statt 4). Bei sehr vielen
  Kandidaten laufen im ungünstigen Fall sechs Modellaufrufe gleichzeitig.
  Das ist gewollt — die vier zusätzlichen sind die billigen —, aber es ist
  eine Erhöhung.
- **Die Liste der technischen Fehler ist eine Aufzählung**, keine Regel. Ein
  neuer Fehlertyp im SDK landet zunächst außerhalb und schlägt durch. Das ist
  die sichere Richtung: Er fällt auf, statt still auszuweichen.
- **ADR 0026 nennt weiterhin fünf Minuten** für den blockierten Platz. Der
  Wert war zum Zeitpunkt jenes ADR richtig; er wird hier richtiggestellt und
  dort nicht rückwirkend geändert.
- **`llm.fundamental` und `llm.report` bleiben ungenutzt.** Die
  Fundamentalanalyse ist seit ADR 0032 deterministisch, der Report Generator
  hat noch keine KI-Hälfte. Beide Profile bekommen trotzdem ein
  Ausweichmodell, damit sie es haben, sobald sie gebraucht werden.
