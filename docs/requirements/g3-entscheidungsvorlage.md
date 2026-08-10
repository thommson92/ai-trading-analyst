# G3-Entscheidungsvorlage — Lizenz-/Nutzungsbedingungen und R2-Betriebsmodell

- Status: **Gate G3 offen.** Dieses Dokument ist die Entscheidungsvorlage,
  nicht die Entscheidung selbst. Es enthält keine Freigabe und keine
  Bewertung, die einer Entscheidung vorgreift.
- Zweck: Vollständige, in sich geschlossene Grundlage für die beiden noch
  offenen Entscheidungsstränge, die vor Gate G3 (produktive
  TradingView-Integration) geklärt werden müssen — mit Prüfschritten,
  Verantwortlichkeiten und Entscheidungskriterien je Strang.
- Herkunft: konsolidiert aus dem Gate-G2-Spikebericht
  (`spikes/tradingview-cdp/REPORT.md`, Branch `spike/tradingview-cdp`,
  Abschnitte 16 und 18) und Doc 10, Paragraph 3 der Aufgabenstellung
  ("Bestandene technische Tests belegen keine vertragliche oder rechtliche
  Zulässigkeit").
- **Ausdrücklich außerhalb des Umfangs dieses Dokuments:** jede Änderung am
  Spike-Branch, jede Implementierung, jede TradingView-Automatisierung. Dies
  ist reine Entscheidungsvorbereitung.

## Kennzeichnung in diesem Dokument

Jeder Prüfschritt ist als **OFFEN** markiert, bis er durchgeführt und sein
Ergebnis hier nachgetragen wurde. Kein Punkt gilt stillschweigend als
erledigt — Statusänderungen werden ausdrücklich eingetragen, mit Datum und
Verweis auf das jeweils entstehende ADR.

---

## 1. Warum zwei getrennte Entscheidungsstränge

Der Spikebericht unterscheidet ausdrücklich zwei Dimensionen, die nicht
vermischt werden dürfen (REPORT.md, Abschnitt 18):

1. **Technische Stabilität** — mit `GO_WITH_LIMITATIONS` bereits
   abgeschlossen (Gate G2, bestätigt).
2. **Rechtliche/vertragliche Zulässigkeit** — in Gate G2 bewusst nicht
   bewertet.

Zusätzlich hat Gate G2 ein drittes, unabhängiges offenes Risiko konkret und
unumstößlich gemacht:

3. **Das Betriebsmodell für unbeaufsichtigten Betrieb (R2)** — TradingView
   Desktop ist eine GUI-Anwendung und kann nicht in Windows Session 0
   laufen. Ein täglicher, unbeaufsichtigter Produktivlauf erfordert deshalb
   technisch Windows-Autologon oder eine gleichwertige Alternative. Diese
   Entscheidung ist eine Sicherheits-/Betriebsentscheidung, keine
   Lizenzfrage, und wird deshalb als eigener Strang geführt.

Beide Stränge sind **unabhängig voneinander blockierend**: Ein GO in Strang
A ersetzt kein GO in Strang B, und umgekehrt. Gate G3 braucht ein GO in
**beiden**.

---

## 2. Strang A — Lizenz-/Nutzungsbedingungen

### 2.1 Kontext

Der gewählte technische Weg (Chrome DevTools Protocol gegen die lokal
installierte, mit dem eigenen Account angemeldete TradingView-Desktop-App)
funktioniert nachweislich (Gate G2). Ob er mit den TradingView-
Nutzungsbedingungen vereinbar ist, wurde bewusst nicht geprüft — eine
technische Machbarkeitsstudie kann und darf diese Frage nicht mitbeantworten
(Nutzervorgabe, siehe Sprint-0-Auftrag).

Relevante Eckpunkte des geprüften Zugriffswegs, die für die rechtliche
Bewertung wichtig sind (rein technische Fakten aus dem Spike, keine
rechtliche Einordnung):

- Es wird ausschließlich die bereits angemeldete, eigene Sitzung des
  Account-Inhabers verwendet — keine Umgehung von Login/Zahlschranken, keine
  fremden Zugangsdaten (REPORT.md, Abschnitt 3b).
- Es werden keine Server-Endpunkte direkt angesprochen; der Zugriff erfolgt
  ausschließlich über die lokal laufende Desktop-App und das darin ohnehin
  aktivierbare Chrome-DevTools-Protocol.
- Es werden Marktdaten (Kurswerte, Indikatorwerte) ausgelesen und für den
  eigenen, in Doc 01 beschriebenen Zweck (persönliches Analyse-Tool,
  keine Weitergabe an Dritte, keine Order-Ausführung) gespeichert.
- Es findet keine Veränderung der TradingView-Anwendung statt (kein
  Reverse-Engineering im Sinne von Codeänderung, ausschließlich Auslesen
  über eine von der Anwendung selbst bereitgestellte Debug-Schnittstelle).

### 2.2 Prüfschritte

| # | Schritt | Status |
|---|---|---|
| A1 | Aktuelle TradingView-Nutzungsbedingungen (Website) beschaffen und Datum/Version notieren | OFFEN |
| A2 | Separate Lizenzbedingungen/EULA der Desktop-App (Microsoft-Store-Eintrag) beschaffen, falls abweichend von A1 | OFFEN |
| A3 | Beide Dokumente gezielt auf folgende Punkte durchsehen: Verbote von "automated access" / "scraping" / Bots; Verbote oder Einschränkungen zur Nutzung von Debugging-/Automatisierungsschnittstellen; Unterscheidung privater vs. kommerzieller Nutzung; Bestimmungen zu Speicherung/Weiterverarbeitung bezogener Daten; Kündigungs- und Sperrungsklauseln bei Verstößen | OFFEN |
| A4 | Fundstellen wörtlich zitieren und einer laienverständlichen Einschätzung gegenüberstellen (nicht nur "passt"/"passt nicht", sondern die zitierte Klausel plus Begründung) | OFFEN |
| A5 | Bei verbleibender Unsicherheit: Entscheidung, ob externe Rechtsberatung eingeholt wird, abhängig von Risikotoleranz und geplanter Tragweite (rein privates Tool vs. spätere kommerzielle Nutzung) | OFFEN |
| A6 | Ergebnis als eigenständiges ADR dokumentieren, mit Datum/Version der geprüften Nutzungsbedingungen (ToS ändern sich — das ADR gilt nur für den geprüften Stand) | OFFEN |
| A7 | Wiedervorlage festlegen: erneute Prüfung bei jeder wesentlichen TradingView-Vertragsänderung oder spätestens jährlich | OFFEN |

### 2.3 Verantwortlichkeiten

Diese Bewertung ist eine geschäftliche/persönliche Risikoentscheidung des
Projektinhabers (Nutzer) und wird von ihm getroffen — nicht von Claude Code.
Claude Code kann bei A1–A4 unterstützen (Beschaffung, Strukturierung,
Gegenüberstellung von Fundstellen), trifft aber keine eigene rechtliche
Bewertung und keine Empfehlung, die als Rechtsberatung verstanden werden
könnte. Bei A5 entscheidet der Nutzer allein, ob externe Rechtsberatung
nötig ist.

### 2.4 Entscheidungskriterien

**GO**, wenn alle folgenden Punkte zutreffen:

- Kein explizites Verbot des geprüften Zugriffswegs (CDP gegen die eigene,
  lokal laufende, mit dem eigenen Account angemeldete Desktop-App) in den
  gültigen Nutzungsbedingungen gefunden.
- Die geplante Nutzung bleibt innerhalb des als zulässig erachteten Verwendungszwecks
  (insbesondere: persönliche, nicht-kommerzielle Nutzung durch den
  angemeldeten Account-Inhaber selbst, keine Weitergabe an Dritte).
- Das verbleibende Auslegungsrisiko (Nutzungsbedingungen sind selten
  eindeutig zu jedem denkbaren technischen Detail) ist bewusst benannt und
  vom Nutzer akzeptiert.

**NO_GO**, wenn mindestens einer der folgenden Punkte zutrifft:

- Ein ausdrückliches Verbot von automatisiertem Zugriff, Scraping oder der
  Nutzung von Debugging-/Automatisierungsschnittstellen wird gefunden, das
  den geprüften Weg erkennbar einschließt.
- Die geplante Nutzung überschreitet den als zulässig erachteten
  Verwendungszweck (z. B. bei einer späteren kommerziellen Weiterverwendung
  ohne erneute Prüfung).
- Der Nutzer ist nach Prüfung nicht bereit, das verbleibende
  Auslegungsrisiko zu tragen.

---

## 3. Strang B — R2-Betriebsmodell/Autologon

### 3.1 Kontext

Gate G2 hat die technische Notwendigkeit bereits geklärt (REPORT.md,
Abschnitt 12): TradingView Desktop braucht für den Betrieb — auch nur zum
Anzeigen und Auslesen von Daten — eine echte, interaktive
Windows-Desktop-Sitzung. Ein Scheduler, der einen Lauf startet, während
niemand am Server angemeldet ist, funktioniert nur, wenn der Server sich
selbst automatisch an einer solchen Sitzung anmeldet (Windows-Autologon)
oder eine gleichwertige Alternative existiert. Reine Windows-Dienste bzw.
Aufgabenplanung "unabhängig von der Anmeldung ausführen" reichen nicht, da
sie GUI-Anwendungen wegen der Windows-Session-0-Isolation nicht rendern
können — das ist in diesem Spike nicht nur behauptet, sondern strukturell so
angelegt (Projektplan, Risiko R2).

Autologon bedeutet technisch: ein Zugangsdatum (Passwort des
Autologon-Kontos) wird dauerhaft auf dem Server hinterlegt, entweder im
Klartext (Windows-Bordmittel, Registry-Schlüssel `AutoAdminLogon`/
`DefaultPassword`) oder verschlüsselt als LSA-Secret (Sysinternals-Tool
"Autologon") — in beiden Fällen ein bei physischem oder administrativem
Zugriff auf den Server extrahierbares Geheimnis.

### 3.2 Prüfschritte

| # | Schritt | Status |
|---|---|---|
| B1 | Bedrohungsmodell des Windows-Servers aktualisieren: wer hat physischen und administrativen Zugriff, ist der Server ausschließlich für dieses Projekt reserviert oder Mehrzwecksystem, wie ist er netzwerkseitig abgesichert | OFFEN |
| B2 | Autologon-Optionen technisch gegenüberstellen: Windows-Bordmittel (Klartext-Passwort in Registry) vs. Sysinternals-Autologon (LSA-Secret, nicht klartextlesbar für normale Registry-Einsicht) vs. sonstige Alternativen | OFFEN |
| B3 | Kompensierende Maßnahmen festlegen: dediziertes, rechte-minimiertes Betriebskonto statt Administrator-Konto; Datenträgerverschlüsselung (BitLocker), damit ein gestohlener/kopierter Datenträger das Geheimnis nicht trivial preisgibt; Netzwerksegmentierung/Firewall (Server nicht von außen erreichbar); Login-Monitoring/Alerting bei unerwarteten An-/Abmeldungen; Passwortrotation | OFFEN |
| B4 | Erneut gegenprüfen, ob eine Alternative ohne Autologon technisch tragfähig ist (z. B. ein dauerhaft angemeldeter, nie abgemeldeter, nur gesperrter Zustand ohne Neustart — deckt aber keinen Windows-Neustart ab, siehe REPORT.md Abschnitt 11/12) — Ergebnis: trägt nur, solange kein Neustart nötig wird, kein vollwertiger Ersatz | OFFEN |
| B5 | Gewählte Konfiguration auf einem Test-/Kopie-System einrichten und per echtem Server-Neustart verifizieren (Debug-Port automatisch erreichbar, ohne manuelle Anmeldung) — analog zum in REPORT.md Abschnitt 11 dokumentierten Testmuster | OFFEN |
| B6 | Entscheidung inkl. Restrisikobewertung als eigenständiges ADR dokumentieren | OFFEN |

### 3.3 Verantwortlichkeiten

Diese Entscheidung betrifft die physische und betriebliche Sicherheit der
eigenen Server-Infrastruktur des Nutzers und wird von ihm getroffen. Claude
Code kann bei B1–B4 die technischen Optionen recherchieren und
gegenüberstellen sowie bei B5 (Konfiguration, Testdurchführung) und B6
(Dokumentation) unterstützen, **sobald eine Entscheidung getroffen ist** —
nicht davor, und nicht durch eigenmächtiges Einrichten von Autologon oder
vergleichbaren Zugangsdaten-Mechanismen ohne vorherige ausdrückliche
Anweisung.

### 3.4 Entscheidungskriterien

**GO**, wenn alle folgenden Punkte zutreffen:

- Eine konkrete Autologon-/Betriebsmethode ist ausgewählt, ihr
  Restrisiko ist benannt und vom Nutzer bewusst akzeptiert.
- Mindestens die Kompensationsmaßnahmen aus B3 (rechte-minimiertes Konto,
  Datenträgerverschlüsselung) sind umgesetzt oder ihre Nichtumsetzung ist
  bewusst begründet.
- B5 (Neustart-Test ohne manuelle Anmeldung) ist erfolgreich durchgeführt.

**NO_GO**, wenn mindestens einer der folgenden Punkte zutrifft:

- Der Server ist ein Mehrzwecksystem mit Zugriff durch Dritte, bei dem das
  Autologon-Risiko nicht tragbar ist, und keine gleichwertige technische
  Alternative existiert.
- Der Neustart-Test (B5) schlägt fehl oder liefert keinen unbeaufsichtigt
  erreichbaren Debug-Port.
- Der Nutzer ist nach Abwägung nicht bereit, ein dauerhaft auf dem Server
  hinterlegtes Zugangsdatum zu akzeptieren — in diesem Fall bleibt R2 ein
  strukturelles Ausschlusskriterium für den CDP-Ansatz insgesamt, und der
  im Spikebericht angelegte Fallback-Vergleich (REPORT.md, Abschnitt
  "Fallback-Vergleich") wird statt Gate G3 die nächste sinnvolle
  Untersuchung.

---

## 4. Freigabe-Checkliste (Gate G3)

| Strang | Status |
|---|---|
| A — Lizenz-/Nutzungsbedingungen | OFFEN |
| B — R2-Betriebsmodell/Autologon | OFFEN |

**Gate G3 ist erst freigegeben, wenn beide Stränge unabhängig voneinander
GO erreicht haben.** Ein GO in nur einem Strang genügt nicht. Solange
mindestens ein Strang OFFEN oder NO_GO ist, gilt weiterhin: keine
produktive TradingView-Integration, kein Sprint 1C, keine
`TradingViewMarketDataProvider`-Implementierung.
