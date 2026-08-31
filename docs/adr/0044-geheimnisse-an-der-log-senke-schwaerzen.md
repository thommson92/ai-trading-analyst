# ADR 0044: Geheimnisse werden an der Log-Senke geschwärzt

- Status: Angenommen
- Datum: 2026-08-31

## Kontext

CLAUDE.md, Abschnitt Sicherheit: „Keine API-Schlüssel oder Passwörter im Code
oder in `config/default.yaml`. Geheimnisse ausschließlich über
Umgebungsvariablen mit Präfix `ATA_`." Diese Regel ist eingehalten — und sie
deckt den Fall nicht ab, um den es hier geht: Ein Geheimnis, das korrekt aus
der Umgebung kommt, kann trotzdem **wieder hinausgeschrieben** werden.

Finnhub nimmt den Zugangsschlüssel als Query-Parameter `token`. Damit steht er
in der URL. Gemessen, nicht vermutet — drei Kanäle:

| # | Kanal | Wann | Vorher |
|---|---|---|---|
| 1 | Text der `httpx`-Ausnahme, übernommen in die Vertragsausnahme | nur im Fehlerfall | **seit dem ersten Tag offen**, am 2026-08-30 geschlossen |
| 2 | **Die eigene Anfragezeile von `httpx`** (`HTTP Request: GET …&token=… "200 OK"`) | **bei jedem Abruf** | offen |
| 3 | Die `__cause__`-Kette hinter einer bereits geschwärzten Meldung | bei jedem `_logger.exception` | offen |

Kanal 2 ist der schwerwiegende. `httpx` protokolliert auf `INFO`,
`config/default.yaml` steht auf `level: INFO`. Der Schlüssel stand damit nicht
im Ausnahmefall im Protokoll, sondern in **jeder erfolgreichen Anfrage** —
rund zweihundert Zeilen je Tageslauf, auf `stdout` und in jeder Datei, in die
jemand die Ausgabe umleitet.

Kanal 3 ist der lehrreiche: Die Schwärzung der Fehlermeldung vom 2026-08-30
war korrekt und nützte hier nichts. `raise … from error` hält die auslösende
Ausnahme als `__cause__` fest; `_logger.exception` — an fünf Stellen in
`run_analysis` — formatiert die ganze Kette, und die Ursache trägt die
unveränderte URL.

## Entscheidung

**Die Schwärzung sitzt an der Senke, nicht an der einzelnen Meldung.**

1. `observability/secret_redaction.py` führt eine Anmeldung bekannter
   Geheimnisse (`register_secret`) und entfernt sie aus einem fertigen Text
   (`redact_registered`).
2. **Beide Log-Formatter** lassen ihre **fertige Zeile** hindurchlaufen —
   nach dem Anhängen des Tracebacks und der Zusatzfelder. Damit sind Meldung,
   Ausnahmekette und **fremde Zeilen** gleichermaßen abgedeckt.
3. `load_secrets` meldet **jeden gesetzten Wert** aus `Secrets` an, nicht nur
   den Finnhub-Schlüssel. Es ist die einzige Stelle, an der der Betrieb
   Geheimnisse lädt; CLI, API und Scheduler gehen alle hindurch.
4. Die Schwärzung der Fehlermeldung in beiden Finnhub-Adaptern **bleibt**. Sie
   deckt einen Weg ab, den die Senke nicht sieht: eine Ausnahme, die als Text
   auf `stderr` oder in eine CLI-Ausgabe geht, ohne durch das Logging zu
   laufen.
5. Ein Geheimnis unter acht Zeichen wird **nicht** angemeldet, sondern
   gemeldet. Angemeldet zerschriebe es jede Zeile, in der dieselben Zeichen
   zufällig vorkommen, ohne etwas zu schützen.

### Warum das Anmelden nicht abbricht

Ein zu kurzer Wert könnte auch ein Startfehler sein — die Umgebungsvariable
ist dann vermutlich falsch gesetzt. Dagegen steht: **Diese Schicht ist ein
Schutznetz, und ein Schutznetz darf nicht die Ursache dafür sein, dass ein
Lauf nicht startet.** Ob ein Wert plausibel ist, prüft `Secrets` — nicht die
Schwärzung. Deshalb Warnung und Überspringen, nicht Abbruch.

## Was hiermit nicht entschieden ist

**Der Wechsel auf `X-Finnhub-Token` bleibt offen.**

Finnhub akzeptiert den Schlüssel auch als Header. Dann stünde er in keiner
URL, und alle drei Kanäle wären **an der Wurzel** trocken statt an der Senke
gefiltert. Das ist der bessere Weg.

Er wird hier trotzdem nicht gegangen: Er ändert die Authentisierung einer
laufenden produktiven Anbindung und lässt sich nur gegen den echten Dienst
prüfen — ein Fehlschlag träfe den Earnings-Filter im Tageslauf. Dieser
verhält sich zwar weich (`EarningsFilterStatus.UNKNOWN`, `provider_error`),
aber ein stillschweigend blinder Filter ist kein guter Preis für eine
Aufräumarbeit.

Beides schließt sich nicht aus. Die Schwärzung wirkt für **jedes** Geheimnis
und **jeden** Anbieter — auch für den LLM-Schlüssel, den Telegram-Token und
die Datenbank-URL, die alle nichts mit Finnhub zu tun haben. Sie bleibt nach
einem Wechsel auf den Header sinnvoll.

## Konsequenzen

- Ein neuer Anbieter mit einem Geheimnis in der URL ist **von selbst**
  abgedeckt, sobald sein Schlüssel in `Secrets` steht. Das ist der eigentliche
  Gewinn gegenüber einer Schwärzung je Adapter: Der Schutz hängt nicht mehr
  daran, dass der nächste Adapter daran denkt.
- Der Schutz hängt daran, dass Geheimnisse über `load_secrets` geladen werden.
  Ein direkt gebautes `Secrets()` — wie in Tests üblich — meldet nichts an.
  Für den Betrieb ist das der richtige Zuschnitt; für einen künftigen zweiten
  Einstiegspunkt ist es eine Fußangel und hier festgehalten.
- Protokolle bleiben lesbar: Endpunkt, Symbol und Statuscode stehen weiterhin
  in der Zeile, nur der Wert des Geheimnisses ist `***`.
- **Bereits geschriebene Protokolle sind nicht rückwirkend sauber.** Wo
  Ausgaben des Servers in Dateien gelandet sind, enthalten sie den Schlüssel
  im Klartext. Konsequenz: Der Finnhub-Schlüssel ist zu erneuern, und
  vorhandene Protokolldateien sind zu prüfen.

## Alternativen

**Den `httpx`-Logger stummschalten** (`logging.getLogger("httpx")` auf
`WARNING`). Löst Kanal 2, nicht Kanal 3, und nimmt die Anfragezeile ganz weg —
sie ist beim Suchen eines Problems nützlich. Verworfen.

**Nur je Adapter schwärzen**, wie am 2026-08-30. Der Befund selbst ist das
Gegenargument: Genau diese Lösung war in Kraft, während zwei von drei Kanälen
offen standen.
