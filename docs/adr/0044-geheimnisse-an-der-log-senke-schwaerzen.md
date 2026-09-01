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
3. **`Secrets` selbst** meldet in `model_post_init` jeden gesetzten Wert an,
   nicht nur den Finnhub-Schlüssel. Die Anmeldung hängt damit an der
   *Entstehung* des Geheimnisses, nicht an einem von mehreren Ladewegen.
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
- Es gibt **keinen** Weg, an der Anmeldung vorbeizubauen. Wer ein `Secrets`
  in der Hand hält, hat es damit angemeldet.
- Protokolle bleiben lesbar: Endpunkt, Symbol und Statuscode stehen weiterhin
  in der Zeile, nur der Wert des Geheimnisses ist `***`.
- **Bereits geschriebene Protokolle sind nicht rückwirkend sauber.** Wo
  Ausgaben in Dateien gelandet sind, enthalten sie den Schlüssel im Klartext.
  Konsequenz: Schlüssel erneuern und vorhandene Protokolldateien prüfen.

## Alternativen

**Den `httpx`-Logger stummschalten** (`logging.getLogger("httpx")` auf
`WARNING`). Löst Kanal 2, nicht Kanal 3, und nimmt die Anfragezeile ganz weg —
sie ist beim Suchen eines Problems nützlich. Verworfen.

**Nur je Adapter schwärzen**, wie am 2026-08-30. Der Befund selbst ist das
Gegenargument: Genau diese Lösung war in Kraft, während zwei von drei Kanälen
offen standen.


## Nachtrag vom 2026-08-31: die erste Fassung griff nicht

Die Anmeldung saß zunächst in `load_secrets`, mit der Begründung, das sei
„die einzige Stelle, an der der Betrieb Geheimnisse lädt". Das war falsch.
**Das CLI baut `Secrets()` an sechs Stellen selbst** und ging daran vorbei.

Die Fußangel stand im ersten Text dieses ADR sogar wörtlich — als
Konsequenz, dass „ein direkt gebautes `Secrets()` — wie in Tests üblich —
nichts anmeldet". Der Zusatz „wie in Tests üblich" war die Fehleinschätzung:
Es ist der Normalfall des CLI.

Gefunden hat es die Serverprobe, die dieses ADR selbst vorgeschrieben hatte
(„ob in der Ausgabe irgendwo der Zugangsschlüssel steht"). Der erste
produktive Finnhub-Abruf am 2026-08-31 gab aus:

```
httpx: HTTP Request: GET https://finnhub.io/...&token=<echter Schlüssel> "HTTP/1.1 200 OK"
```

Die Tests waren grün, weil sie `load_secrets` prüften — den Weg, den das CLI
nicht nimmt. Ein Test, der die Verdrahtung an *einem* Einstiegspunkt prüft,
sagt nichts über die anderen.

Zwei Änderungen daraus:

1. Die Anmeldung wandert nach `Secrets.model_post_init`. Sie hängt jetzt an
   der Entstehung des Geheimnisses; ein zweiter Ladeweg kann nicht mehr
   danebenliegen.
2. Der Regressionstest baut `Secrets()` **direkt** und läuft in der
   Reihenfolge von `command_ratings`: Logging aufsetzen, Geheimnis laden,
   abrufen. Mutiert man die Anmeldung weg, erscheint die Serverausgabe
   zeichengenau wieder.

Der betroffene Schlüssel wurde erneuert.

## Nachtrag vom 2026-09-01: der Wurzelfix ist umgesetzt

Der als besser, aber ungegangen benannte Weg ist gegangen: Der
Finnhub-Adapter schickt den Schlüssel als `X-Finnhub-Token`-Header
(`infrastructure/finnhub/auth.py`), nicht mehr als Query-Parameter. Damit
steht er in keiner URL — und die drei Kanäle aus dem Kontext (Fehlertext,
`httpx`-Zugriffsprotokoll, Ausnahmekette) sind an der Quelle trocken.

Das Repository-Audit vom 2026-08-23 hat diesen offenen Rest als
Prozessbefund geführt („Symptom statt Ursache?"), das
[Audit 2](../audits/2026-08-31-repository-audit-2.md) als Maßnahme A2-M10.

**Die Schwärzung bleibt.** Sie war nie nur eine Notlösung für Finnhub: Sie
wirkt für jedes registrierte Geheimnis und für Texte, die das System nicht
selbst formuliert hat. Die Entscheidung dieses ADR — Schwärzung an der
Senke statt an der einzelnen Meldung — ist unverändert gültig.

**Am echten Dienst bestätigt** (Server, 2026-09-01, 14:33 UTC):
`cli ratings --symbol AAPL --provider finnhub` liefert
`COMPLETED` mit vier Monatsständen. Die Zugriffszeile, die `httpx` selbst
auf `INFO` schreibt, lautet dabei:

```text
HTTP Request: GET https://finnhub.io/api/v1/stock/recommendation?symbol=AAPL "HTTP/1.1 200 OK"
```

Genau das war der Punkt: **kein `token=` mehr in der URL** — und damit in
keiner der drei Stellen aus dem Kontext. Vorher stand der Schlüssel hier bei
jedem Abruf, rund zweihundertmal je Tageslauf.
