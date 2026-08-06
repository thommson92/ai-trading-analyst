# Claude Code Entwicklungsrichtlinien


## Grundprinzip

Arbeite niemals direkt an großen Features ohne vorher:

1. Anforderungen lesen
2. Architektur prüfen
3. Implementierungsplan erstellen


---

# Codequalität

Pflicht:

- TypeScript strict mode
- Python type hints
- Tests für neue Funktionen
- keine unnötigen Dependencies
- Dokumentation aktualisieren


---

# Entwicklung

Jede Funktion wird in kleinen Schritten umgesetzt.

Nach jedem Feature:

- Tests ausführen
- Code prüfen
- Dokumentation aktualisieren


---

# Architekturregeln

Keine Geschäftslogik im Frontend.

Keine KI-Logik direkt in API-Endpunkten.

Agenten bleiben getrennte Module.


---

# Trading Logik

Technische Signale dürfen niemals durch KI verändert werden.

Die KI bewertet nur:

- Kontext
- Qualität
- Risiko

Die Signaldefinition bleibt deterministisch.


---

# Sicherheit

Keine API Keys im Code.

Alle Secrets über Environment Variables.


---

# Logging

Alle Analyseprozesse müssen nachvollziehbar sein.

Zu speichern:

- Startzeit
- Endzeit
- Fehler
- verwendete Datenquellen
- Agentenergebnisse
