# ADR 0051: Der Research Agent ist im Dauerbetrieb abgeschaltet — Provider-Wert `none`

- Status: Angenommen
- Datum: 2026-09-01

## Kontext

Mit der erstmaligen Aktivschaltung der Aufgabenplanung (2026-09-01) stellte
sich die Frage, welche der beiden LLM-Aufrufe der Dauerbetrieb bezahlt. Der
Technical Agent kostet rund einen halben Cent je Kandidat; der Research
Agent das Hundertfache (~0,52–0,58 USD, gemessen —
[ADR 0023](0023-research-agent-zitierarchitektur.md), Nachträge), und sein
Kostenhebel ist gemessen nicht vorhanden.

Für „Agent aus" gab es bis dahin keinen sauberen Zustand: Die
Provider-Wahl kannte nur `fixture` und `anthropic`
([ADR 0021](0021-ki-anbindung-anthropic-api.md)). `fixture` simuliert aber
einen **funktionierenden** Anbieter — im Scharfbetrieb hätte er 30 % des
Swing-Scores mit identischen Konstanten gefüllt, jede Meldungszeile mit
„Fehlsignalrisiko medium" und den Bericht mit Beispieltexten, alles ohne
Kennzeichnung. Genau die erfundenen Werte, die CLAUDE.md verbietet.

## Entscheidung

1. **Es gibt einen dritten Provider-Wert `none`** für die beiden
   LLM-Agenten (`research.provider`, `technical_agent.provider`). Er
   liefert `UNAVAILABLE` mit Grund `provider_disabled` — denselben Pfad wie
   ein Anbieterausfall: Der Score gewichtet um, der Bericht weist die Lücke
   aus, die Meldung unterdrückt die Zeile. Kein Schlüssel, keine Kosten
   (`infrastructure/disabled.py`).
2. **Der Dauerbetrieb fährt `--research-provider none` und
   `--technical-agent-provider anthropic`.** Die Recherche bleibt als
   Einzelprobe verfügbar (Doc 14, Stufe G Schritt 2); dauerhaft scharf
   geschaltet wird sie durch Ersetzen von `none` durch `anthropic` im
   Aufgabenplanungs-Eintrag.
3. Für die Datenanbieter (Marktdaten, Earnings, Fundamentaldaten, Ratings,
   Optionen) gibt es `none` bewusst **nicht**: Ein Lauf ohne seine
   Pflichtdaten ist kein abgeschalteter Zusatz, sondern ein anderer Lauf.

## Begründung

Die Abschaltung ist eine Kostenentscheidung, keine Qualitätsaussage: Die
Recherche funktioniert ([ADR 0029](0029-research-qualitaet.md)), aber ihr
Preis je Kandidat steht in keinem belegten Verhältnis zu ihrem Beitrag —
die News-Komponente des Scores rechnet ohnehin aus den Analystenvoten
([ADR 0046](0046-empfehlungsstufe-aus-beiden-scores.md)), nicht aus dem
Recherche-Freitext. Ehrlich abschalten schlägt teuer mitlaufen — und
schlägt vor allem das stille Weiterlaufen der Fixture, deren Ergebnisse wie
geprüfte aussehen.

Dieses ADR löst **nichts an ADR 0021/0023 ab**: Anthropic bleibt der
Research-Anbieter, die Zitierarchitektur bleibt maßgeblich — es ruht nur
der tägliche Aufruf.

## Konsequenzen

- Berichtspunkt „Nachrichten" erscheint im Tageslauf als gekennzeichnete
  Lücke (`provider_disabled`); der Swing-Score rechnet mit voller
  Abdeckung, weil keine seiner Komponenten an der Recherche hängt.
- Der geschaltete Stand steht im Doc-14-Abschnitt „Betriebszustand"; die
  Entscheidung, ihn zu ändern, ist ein Ersetzen von `none` durch
  `anthropic` — und umgekehrt jederzeit rückholbar.
- Wer die Recherche wieder dauerhaft einschaltet, übernimmt die gemessenen
  Kosten (~0,55 USD je Kandidat mit freiem Earnings-Fenster) bewusst; ein
  neues ADR braucht das nicht, ein Nachtrag am Betriebszustand genügt.
