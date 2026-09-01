# ADR 0049: Dashboard-MVP nur im eigenen Netz — keine Exposition, keine eigene Authentifizierung

- Status: Angenommen
- Datum: 2026-09-01

## Kontext

F12 — „Wie erfolgt der externe Zugriff auf das Dashboard?" — war die letzte
offene Architekturfrage aus Doc 10 §19 und blockierte Sprint 6 vollständig:
Ohne die Antwort ließ sich weder der API-Ausbau schneiden (Authentifizierung
ja/nein) noch die Container-Frage beantworten, die
[ADR 0036](0036-nativer-windows-betrieb.md) ausdrücklich an den
Dashboard-Sprint vertagt hat. Das Audit vom 2026-08-23 führte den Punkt als
E8, das [Audit 2](../audits/2026-08-31-repository-audit-2.md) als einzige
blockierende Entscheidung für Sprint 6.

Drei Optionen standen zur Wahl: (a) Dashboard nur im lokalen Netz bzw. über
VPN, ohne eigene Authentifizierung; (b) von außen erreichbar hinter
Reverse-Proxy und Login; (c) keine Server-Exposition, stattdessen lokaler
Export an ein Endgerät.

Berührt sind zwei bestehende Festlegungen: Finnhubs Einschränkung L8
([ADR 0017](0017-finnhub-fuer-earnings-und-ratings.md) — keine Weitergabe
abgeleiteter Daten an Dritte) und das Deployment-Gate aus
[ADR 0022](0022-research-agent-quellen.md), das vor jeder externen
Erreichbarkeit eine eigene Entscheidung verlangt.

## Entscheidung

**Option (a): Das Dashboard des MVP ist ausschließlich aus dem eigenen Netz
erreichbar** — lokal auf dem Server oder über das LAN, wahlweise über ein
ohnehin vorhandenes VPN. Es gibt **keine Exposition ins Internet** und
**keine eigene Authentifizierung**. `ATA_SESSION_SECRET` bleibt reserviert
und weiterhin ohne Wirkung.

**Externe Erreichbarkeit und Authentifizierung werden nach stabilem Betrieb
neu bewertet** — dann als eigenes ADR, zusammen mit der
Reverse-Proxy-/Container-Frage aus ADR 0036. Diese Entscheidung ist damit
ausdrücklich eine Stufe, kein Endzustand.

## Begründung

Ohne Exposition existiert kein externes Bedrohungsmodell, das eine
Auth-Schicht abwehren müsste. Authentifizierung **vor** der Exposition zu
bauen wäre Sicherheitsarbeit ohne Gegner — sie verzögerte den ersten
Nutzwert des Dashboards um genau die Komponenten (Login, Sessions,
Secret-Handling im Frontend), die erst die Öffnung nach außen wirklich
braucht. Der Fernzugang für unterwegs existiert bereits: die
Telegram-Ergebnismeldung ([ADR 0047](0047-scores-in-der-ergebnismeldung.md)),
die bewusst dünn gehalten ist.

Option (b) bleibt der wahrscheinliche Ausbau, sobald der Betrieb stabil
läuft; Option (c) löste das falsche Problem — die Analyseergebnisse liegen
auf dem Server, und ein Export-Umweg machte jede Aktualisierung zum
Handgriff.

## Konsequenzen

- **Sprint 6 ist entsperrt.** API-Ausbau (Endpunkte für Berichte und
  Historie, Pagination) und Frontend gegen `stock_reports` können ohne
  Auth-Unterbau beginnen; die API bindet weiterhin nur an lokale
  Schnittstellen.
- Finnhub L8 bleibt gewahrt, solange nichts das eigene Netz verlässt — die
  Weitergabefrage stellt sich erst mit der Expositions-Entscheidung wieder.
- `ATA_SESSION_SECRET` und das Deployment-Gate aus ADR 0022 bleiben
  bestehen und warten auf das Folge-ADR zur Exposition.
- Wer das Dashboard von unterwegs will, braucht bis dahin ein VPN ins
  eigene Netz — eine bewusste Unbequemlichkeit, keine Lücke.
- In der „Offene Entscheidungen"-Liste (`docs/adr/README.md`) war F12 der
  letzte Punkt, der einen Sprint blockierte. Offen bleiben dort nur die
  zwei Fundamental-Fragen (Vergleichsgruppe, Stichtagsbindung aus
  [ADR 0034](0034-fundamentaldaten-nach-dem-watchlist-lauf.md) L3) — beide
  blockieren nichts.
