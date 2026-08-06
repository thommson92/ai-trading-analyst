# ADR 0005: Konfiguration in YAML, Geheimnisse aus der Umgebung

- Status: Angenommen
- Datum: 2026-08-06

## Kontext

Doc 10 §17 gibt eine zentrale YAML-Konfiguration vor und verlangt, dass
Konfigurationsänderungen protokolliert werden. Doc 10 §13 verlangt, dass
Geheimnisse nicht im Repository liegen.

Beides in einer Datei zu mischen führt erfahrungsgemäß dazu, dass irgendwann
ein Passwort in der Git-Historie steht — und nachträglich aus der Historie zu
entfernen ist mühsam.

## Entscheidung

**Zwei getrennte Quellen:**

- `config/default.yaml` — fachliche Werte, eingecheckt, ohne jedes Geheimnis.
  Validiert gegen `AppConfig` (Pydantic).
- Umgebungsvariablen mit Präfix `ATA_` — ausschließlich Geheimnisse, gelesen
  über `Secrets` (pydantic-settings). `.env.example` ist eingecheckt und
  enthält nur Platzhalter; `.env` ist ab dem ersten Commit in `.gitignore`.

**Vier Eigenschaften, die die Umsetzung von einem simplen Config-Loader
unterscheiden:**

1. **Unbekannte Schlüssel sind ein Startfehler** (`extra="forbid"`). Ein
   Tippfehler wie `required_signal_cout` würde sonst still zum Default führen
   und die Kandidatenregel unbemerkt verändern.
2. **Querbezüge werden validiert.** Die Sitzungsdauer muss ohne Rest durch den
   Timeframe teilbar sein; der konfigurierte Earnings-Wert muss innerhalb der
   dokumentierten Grenzen liegen; das Wartebudget muss mindestens einen
   Pollversuch zulassen. Eine in sich widersprüchliche Konfiguration startet
   nicht.
3. **Fingerprint über den Dateiinhalt** (SHA-256, gekürzt) — erfüllt die
   Protokollpflicht aus Doc 10 §17, ohne die Datei selbst zu loggen.
4. **Fehlende Geheimnisse scheitern benannt.** `Secrets.require("database_url")`
   nennt im Fehlertext die erwartete Umgebungsvariable, statt ein stilles `None`
   weiterzureichen.

## Begründung

Ein Konfigurationsfehler in diesem System ist besonders unangenehm, weil er
nicht zum Absturz führt, sondern zu plausibel aussehenden falschen Ergebnissen:
Ein falscher Timeframe erzeugt Signale, die niemand als falsch erkennt. Deshalb
ist die Konfiguration bewusst streng — sie soll früh und laut scheitern.

`SecretStr` verhindert außerdem, dass ein versehentlich geloggtes
Settings-Objekt Zugangsdaten preisgibt; ein Test sichert das ab.

## Konsequenzen

- Jede neue Konfigurationsoption braucht ein Feld im Schema; YAML allein
  genügt nicht.
- Ein Test prüft, dass `config/default.yaml` keine geheimnisverdächtigen
  Schlüssel enthält (`password`, `api_key`, `token`, `secret`).
- Deployments setzen Geheimnisse über Umgebungsvariablen, nie über Dateien im
  Repository.
