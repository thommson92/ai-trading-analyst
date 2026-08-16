# ADR 0021: KI-Anbindung -- Konfigurationsmechanik vorgeschlagen, Anbieterwahl offen

- Status: Vorgeschlagen
- Datum: 2026-08-16

## Kontext

Sprint 3 (Filter & Backtesting) ist mit dem Earnings-Filter (ADR 0020, PR #24)
und der historischen Signalprüfung fachlich abgeschlossen. Der nächste
Sprint laut [Roadmap](../03%20-%20Roadmap.md) ist Sprint 4 -- KI-Analyse:
Research Agent, Technical Agent, Fundamental Agent, Report Generator (Doc 06).

CLAUDE.md sperrt den Beginn ausdrücklich, bis ein ADR steht: *"Ebenfalls noch
nicht zu beginnen: produktive Datenprovider und die KI-Integration. Beide
brauchen zuerst ein ADR."* Doc 10 §19 führt das als offene Frage F11: *"Welcher
KI-Anbieter beziehungsweise welches Modell wird für welche Analyseaufgabe
verwendet?"*

Vier Vorgaben stehen bereits fest und sind nicht Gegenstand dieses ADR,
sondern binden es:

- **CLAUDE.md "KI-Anbindung":** Anbieter, Modell und Modellversion sind
  ausschließlich konfigurierbar. Domain- und Application-Code dürfen von
  keinem konkreten Modell abhängen -- sie kennen nur ein Modellprofil je
  Aufgabe, inklusive Fallback. Die verwendete Modellversion wird an jedem
  Ergebnis gespeichert.
- **CLAUDE.md "Die zentrale Regel":** Ein Sprachmodell erläutert,
  zusammenfasst, bewertet Risiken und begründet Empfehlungen. Es verändert
  keine Signalregeln, erfindet keine Marktdaten und ersetzt keine
  deterministische Berechnung.
- **Doc 10 §10:** Kontrollierter Workflow mit strukturierten Ein- und
  Ausgaben, gegen ein festes Schema validiert. Ein Agenten-Framework
  (LangGraph o. ä.) nur bei konkretem Vorteil (wiederaufnehmbare Workflows,
  Retry-Logik, nachvollziehbare Tool-Aufrufe) -- nicht standardmäßig.
  Quellenbindung für Nachrichten/Analystenmeinungen/Kursziele/
  Fundamentaldaten. Halluzinationsschutz: fehlt eine belastbare Grundlage,
  lautet das Ergebnis `INSUFFICIENT_DATA`, nie ein plausibel wirkender
  Ersatzwert.
- **CLAUDE.md "Sicherheit" / Doc 10 §13:** Externe Research-Inhalte gelten als
  nicht vertrauenswürdig, werden als markierte Daten übergeben, nie als
  Instruktion. Der Research-Kontext erhält keine Tool-Rechte. Scores werden
  nie direkt aus LLM-Freitext übernommen.

`.env.example` reserviert bereits `ATA_LLM_API_KEY` als Platzhalter (seit
Sprint 0), bisher ungenutzt.

Die vier geplanten Aufgaben unterscheiden sich in ihrem Risikoprofil:

| Aufgabe | Tool-/Netzzugriff | Kritischster Punkt |
|---|---|---|
| Research Agent | ja -- externe Quellen | Prompt-Injection aus nicht vertrauenswürdigem Research-Kontext |
| Technical Agent | nein -- interpretiert nur bereits deterministisch berechnete Werte | Darf Signale nicht umdeuten |
| Fundamental Agent | evtl. -- Kennzahlenabruf | Quellenbindung |
| Report Generator | nein -- fasst bereits validierte Strukturdaten zusammen | Sprachqualität, keine neuen Fakten |

## Entscheidung

**Zwei getrennte Fragen.** Die Konfigurationsmechanik lässt sich aus den oben
zitierten, bereits bindenden Vorgaben ableiten und wird hier als Vorschlag
festgelegt. Die Anbieter-/Modellwahl selbst ist eine Kosten- und
Vertragsentscheidung, die dieses ADR bewusst **nicht** einseitig trifft --
siehe "Offene Punkte" unten.

### Konfigurationsmechanik (Vorschlag)

Neue Sektion `llm` in `config/default.yaml`/`AppConfig`, im Muster von
`MarketDataConfig`/`EarningsFilterConfig`:

```python
class ModelProfile(_Section):
    """Ein Modell fuer eine Analyseaufgabe, mit Ausweichmodell."""

    provider: str
    model: str
    fallback_provider: str | None = None
    fallback_model: str | None = None


class LlmConfig(_Section):
    """Modellprofile je Analyseaufgabe (CLAUDE.md "KI-Anbindung")."""

    research: ModelProfile
    technical: ModelProfile
    fundamental: ModelProfile
    report: ModelProfile
```

- Domain- und Application-Code referenzieren nur einen Aufgabennamen (z. B.
  über ein `AnalysisTask`-Enum), nie einen konkreten Provider-SDK-Typ -- das
  Provider-SDK bleibt Infrastructure, analog zu
  `infrastructure/ibkr`/`infrastructure/finnhub`.
- Je Aufgabe ein `LlmProvider`-Port (Protocol) in der jeweiligen
  `domain/<aufgabe>/ports.py`, Muster wie `EarningsProvider`: eine
  strukturierte Anfrage rein, ein gegen ein festes Schema validiertes
  Ergebnis raus (Doc 10 §10).
- Jedes KI-Ergebnis speichert `provider`, `model` und `model_version` als
  eigene Felder -- Audit-Trail-Pflicht aus Doc 10 §12 ("welche Modell- und
  Prompt-Version verwendet wurde"). Ein zusätzliches `prompt_version`-Feld
  je Ergebnis deckt die im selben Paragraphen geforderte Prompt-Versionierung
  ab.
- Secrets: `ATA_LLM_API_KEY` bleibt der Standardfall. Werden mehrere Anbieter
  gleichzeitig produktiv (z. B. günstigeres Modell für den Report, teureres
  für Research), kommt je Anbieter ein eigener Schlüssel hinzu
  (`ATA_<ANBIETER>_API_KEY`, Muster wie `ATA_FINNHUB_API_KEY`).
- Fallback greift nur bei technischem Versagen (Timeout, Ratenlimit,
  Providerfehler) -- nie als stille Qualitätsminderung ohne Kennzeichnung.
  Welches Modell tatsächlich geantwortet hat, steht im gespeicherten
  Ergebnis, nicht nur im Log.
- Der Research-Kontext (externe, nicht vertrauenswürdige Inhalte) wird als
  Daten-Parameter übergeben, nie in die Systemanweisung eingemischt, und
  erhält keine Tool-Berechtigungen -- konkrete Umsetzung (Prompt-Aufbau,
  Injection-Tests) folgt im jeweiligen Agenten-ADR/Sprint-4-Ticket, nicht
  hier.

### Offene Punkte -- braucht Rückmeldung

F11 fragt nach dem **Anbieter/Modell**, nicht nur nach der Mechanik. Das ist
eine Kosten- und Vertragsentscheidung (laufende Marktbeobachtung, kein
Fixpreis pro Analyse), die dieses ADR offen lässt:

1. Ein Anbieter für alle vier Aufgaben, oder unterschiedliche Modelle je
   Aufgabe (z. B. günstiger für Report-Formatierung, stärker für Research)?
2. Direkt beim Anbieter (z. B. Anthropic-, OpenAI-API) oder über einen
   Router/Aggregator (z. B. OpenRouter), der den Wechsel ohne Code-Änderung
   erlaubt, aber eine zusätzliche Abhängigkeit und Kostenschicht einführt?
3. Grobes Kostenbudget je Tag/Monat -- hängt an der erwarteten Zahl
   qualifizierter Kandidaten nach Screener und Earnings-Filter (nicht an der
   vollen Watchlist von ~190 Symbolen), dazu bisher keine belastbare Zahl.
4. Bereits vorhandener API-Zugang/Vertrag bei einem bestimmten Anbieter?

## Begründung

Die Konfigurationsmechanik lässt sich vollständig aus bereits bestätigten
Vorgaben ableiten (CLAUDE.md, Doc 10 §10/§12/§13) und aus dem etablierten
Muster der letzten beiden Provider-Anbindungen (IBKR, Finnhub) übertragen --
dafür ist keine zusätzliche Nutzerentscheidung nötig. Die Anbieter-/Modellwahl
dagegen ist eine laufende Kostenverpflichtung ohne technischen Zwang zu einer
bestimmten Lösung; sie frühzeitig selbst festzulegen würde CLAUDE.mds eigener
Regel widersprechen, zu solchen Punkten keine Annahmen zu treffen.

## Konsequenzen

- Sprint 4 bleibt gesperrt, bis die "Offenen Punkte" beantwortet sind und
  dieses ADR auf **Angenommen** wechselt (Muster wie ADR 0013 → ADR 0014).
- Die Konfigurationsmechanik kann bereits jetzt ohne Anbieterwahl umgesetzt
  und getestet werden (Schema, Ports, Fallback-Verdrahtung, gespeicherte
  Modellversion) -- mit einem Fake-/Test-Provider, wie bei
  `FixtureMarketDataProvider`/`FixtureEarningsProvider`. Ob das vor der
  Anbieterwahl sinnvoll ist oder auf ein gemeinsames ADR wartet, entscheidet
  der nächste Schritt.
- Jede neue Analyseaufgabe braucht ein eigenes Modellprofil im Schema --
  YAML allein genügt nicht (Muster wie ADR 0005).
