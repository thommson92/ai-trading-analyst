# ADR 0021: KI-Anbindung -- Anthropic API mit Modellprofilen je Analyseaufgabe

- Status: Angenommen
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

### Anbieter und Budget

**Anbieter ist die Anthropic API** (`console.anthropic.com`) -- ein eigenes
Entwicklerkonto mit eigenem API-Key und nutzungsbasierter Abrechnung, **nicht**
identisch mit dem bestehenden Claude-Code-Abo: Konsumenten-/Werkzeug-Abos
(Claude Code, ChatGPT Plus) enthalten kein API-Guthaben. Die Anbindung
verlangt ein separates Konto, unabhängig davon, welcher Anbieter am Ende
gewählt wird.

Ein Router/Aggregator (z. B. OpenRouter) entfällt: Sein einziger Vorteil --
anbieterübergreifender Wechsel ohne Code-Änderung -- entfällt bei einem
einzigen gewählten Anbieter, der zusätzliche Aufpreis pro Token und die
zusätzliche Abhängigkeit wären unbegründet.

**Budget:** hartes monatliches Ausgabenlimit im Anthropic-Konto (Spend Limit),
Zielkorridor 20-30 EUR/Monat. Durch die KI-Pipeline laufen nur Kandidaten, die
Screener **und** Earnings-Filter bestehen -- voraussichtlich eine niedrige
ein- bis zweistellige Zahl pro Tag, nicht die volle Watchlist von ~190
Symbolen. Eine belastbare Kostenzahl gibt es erst nach den ersten produktiven
Läufen; `KI-Tokenverbrauch` ist ohnehin als Pflichtmetrik in Doc 10 §12
vorgesehen und macht die tatsächlichen Kosten früh sichtbar, bevor das Limit
erreicht wird.

**Modellstufung je Aufgabe**, um das Budget einzuhalten: ein günstigeres
Modell für Aufgaben mit geringerer Analysetiefe (Report Generator, Fundamental
Agent, Technical Agent -- interpretiert nur bereits deterministisch berechnete
Werte), ein leistungsfähigeres Modell konzentriert auf den Research Agent, wo
Qualität der externen Recherche und Synthese am stärksten zählt. Die exakten
Modell-Identifier gehören **nicht** in dieses ADR, sondern in
`config/default.yaml` -- CLAUDE.mds eigene Vorgabe verbietet ein konkretes
Modell im Code. Sie sind zum Implementierungszeitpunkt gegen den dann
aktuellen Anthropic-Modellkatalog und dessen Preise zu prüfen, nicht aus
diesem Dokument zu übernehmen, da sich beides laufend ändert.

### Konfigurationsmechanik

Neue Sektion `llm` in `config/default.yaml`/`AppConfig`, im Muster von
`MarketDataConfig`/`EarningsFilterConfig`:

```python
class ModelProfile(_Section):
    """Modell fuer eine Analyseaufgabe, mit Ausweichmodell (gleicher Anbieter)."""

    model: str
    fallback_model: str | None = None


class LlmConfig(_Section):
    """Modellprofile je Analyseaufgabe (CLAUDE.md "KI-Anbindung").

    ``provider`` ist heute immer ``anthropic`` (ADR 0021) -- als Literal
    statt als freies Feld, damit ein Tippfehler beim Start auffaellt statt
    still zu einem falschen Adapter zu fuehren (Muster wie
    ``MarketDataConfig.provider``). Ein zweiter Anbieter braucht eine
    Erweiterung des Literals und damit eine bewusste Code-Aenderung, kein
    stilles Umschalten per Konfiguration.
    """

    provider: Literal["anthropic"] = "anthropic"
    research: ModelProfile
    technical: ModelProfile
    fundamental: ModelProfile
    report: ModelProfile
```

- Domain- und Application-Code referenzieren nur einen Aufgabennamen (z. B.
  über ein `AnalysisTask`-Enum), nie einen konkreten Provider-SDK-Typ -- das
  Anthropic-SDK bleibt Infrastructure, analog zu
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
- Secret: `ATA_LLM_API_KEY` -- ein einzelner Schlüssel genügt, solange es bei
  einem Anbieter bleibt.
- Fallback (`fallback_model`) greift nur bei technischem Versagen (Timeout,
  Ratenlimit, Providerfehler) -- nie als stille Qualitätsminderung ohne
  Kennzeichnung. Welches Modell tatsächlich geantwortet hat, steht im
  gespeicherten Ergebnis, nicht nur im Log.
- Der Research-Kontext (externe, nicht vertrauenswürdige Inhalte) wird als
  Daten-Parameter übergeben, nie in die Systemanweisung eingemischt, und
  erhält keine Tool-Berechtigungen -- konkrete Umsetzung (Prompt-Aufbau,
  Injection-Tests) folgt im jeweiligen Agenten-Ticket in Sprint 4, nicht hier.

## Begründung

Die Konfigurationsmechanik lässt sich vollständig aus bereits bestätigten
Vorgaben ableiten (CLAUDE.md, Doc 10 §10/§12/§13) und aus dem etablierten
Muster der letzten beiden Provider-Anbindungen (IBKR, Finnhub) übertragen.

Anbieter- und Budgetentscheidung sind eine laufende Kostenverpflichtung ohne
technischen Zwang zu einer bestimmten Lösung -- CLAUDE.md verbietet
ausdrücklich, an solchen Punkten Annahmen zu treffen. Beide bestehenden Abos
(ChatGPT Plus, Claude Code) wurden geprüft und scheiden als Kostenquelle aus,
da sie kein API-Guthaben enthalten. Anthropic API wurde gewählt, weil die
Nutzerin/der Nutzer damit bereits vertraut ist (Claude Code) und ein einziger
Anbieter mit gestuften Modellen den Router-Aufpreis vermeidet, ohne die in
CLAUDE.md geforderte Aufgabentrennung (Modellprofil je Aufgabe) aufzugeben.

## Konsequenzen

- Sprint 4 ist mit diesem ADR entsperrt.
- Nächste konkrete Schritte vor der ersten Implementierung: Anthropic-Konto
  mit Spend Limit (20-30 EUR/Monat) einrichten, `ATA_LLM_API_KEY` setzen,
  aktuelle Modell-Identifier und Preise gegen den Anthropic-Katalog prüfen und
  in `config/default.yaml` eintragen.
- Die Research Agent ist laut Doc 10 §6.7 der Pipeline-Einstieg (startet nur
  für Kandidaten, die Screener und Earnings-Filter bestanden haben) -- naheliegender
  erster Baustein für Sprint 4, mit dem stärkeren Modellprofil.
- Jede neue Analyseaufgabe braucht ein eigenes Modellprofil im Schema --
  YAML allein genügt nicht (Muster wie ADR 0005).
- Token-Verbrauch und Kosten müssen von Anfang an geloggt werden (Doc 10
  §12), damit das Budget nicht erst beim Erreichen des Spend Limits auffällt.
