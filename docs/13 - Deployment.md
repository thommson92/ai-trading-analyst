# Deployment

Beschlossen in [ADR 0036](adr/0036-nativer-windows-betrieb.md). Die
Schritt-für-Schritt-Anleitung steht in
[Doc 14 — Inbetriebnahme und Betrieb](14%20-%20Inbetriebnahme%20und%20Betrieb.md);
hier steht nur, **was** ausgeliefert wird und warum.

## Zielumgebung

Ein Windows-Server. Auf demselben Rechner laufen die Interactive-Brokers-TWS,
PostgreSQL und der Analyzer.

**Keine Container.** Die TWS ist eine Desktop-Anwendung und braucht eine
angemeldete Windows-Sitzung ([ADR 0018](adr/0018-kein-windows-autologon.md));
sie ist zugleich die Quelle aller Kursdaten. Ein Compose-Verbund müsste sie
außerhalb lassen und wäre damit von vornherein unvollständig. Die Begründung
im Einzelnen steht in ADR 0036.

Containerisierung ist vertagt, nicht verworfen — sie wird zum Dashboard-Sprint
neu bewertet, wenn erstmals etwas entsteht, das ausgeliefert werden muss.

---

## Bestandteile

| Teil | Form |
|---|---|
| Backend | virtuelle Python-Umgebung unter `backend\.venv` |
| Datenbank | lokal installiertes PostgreSQL |
| Auslösung | ein Eintrag in der Windows-Aufgabenplanung |
| Frontend | statischer Export, von der API mit ausgeliefert — siehe unten |

Es gibt keinen Worker-Dienst und keinen Reverse Proxy. Der Dispatcher ist ein
idempotenter Einzelstart, kein Dauerprozess
([ADR 0019](adr/0019-trading-day-dispatcher.md)); ein Proxy setzte externen
Zugriff voraus, und der findet nicht statt
([ADR 0049](adr/0049-dashboard-mvp-nur-lan.md): Das Dashboard bleibt im
eigenen Netz).

**Das Frontend ist ein statischer Export**
([ADR 0052](adr/0052-dashboard-als-statischer-export.md)), den dieselbe
FastAPI-Anwendung mit ausliefert, die die Lese-API bereitstellt: ein
Prozess, ein Port, gleiche Herkunft. Kein Container, kein Node zur Laufzeit
— `npm` baut, mehr nicht. Fehlt der Export, läuft die Anwendung ohne ihn.

Damit bekommt das System mit `uvicorn` seinen **ersten Dauerprozess**,
gestartet bei Systemstart, erreichbar nur im eigenen Netz
([ADR 0049](adr/0049-dashboard-mvp-nur-lan.md)). Der Analyselauf hängt nicht
an ihm, und er kann keinen auslösen
([ADR 0053](adr/0053-lese-api-kein-lauf-ueber-http.md)). Die Einrichtung auf
dem Server beschreibt Doc 14, Stufe J; sie steht noch aus.

Redis ist durch [ADR 0006](adr/0006-kein-redis-im-mvp.md) ausgeschlossen.
Koordiniert wird über PostgreSQL.

---

## Installation und Aktualisierung

Ausschließlich über die Lock-Datei mit Hash-Verifikation, nie über eine
Versionsauflösung auf dem Server
([ADR 0008](adr/0008-reproduzierbare-installation.md),
[ADR 0015](adr/0015-plattformunabhaengige-lock-dateien.md)):

```powershell
git pull
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock.txt
.venv\Scripts\python.exe -m pip install --no-deps -e .
.venv\Scripts\python.exe -m alembic upgrade head
```

Migrationen laufen über Alembic und werden beim Aktualisieren **von Hand**
ausgeführt. Ein zweiter Prozess, der sie parallel anstoßen könnte, existiert
nicht.

Ein Rollback per Image-Tag gibt es nicht. Was schiefgeht, wird über Git
zurückgenommen und neu installiert.

---

## Auslösung

Die Windows-Aufgabenplanung startet `cli dispatch --provider ibkr` im
15-Minuten-Takt über das Nachmittagsfenster. Der Dispatcher entscheidet
selbst, ob heute ein Handelstag ist und ob der Lauf bereits stattgefunden
hat. Die genauen Felder stehen in Doc 14, Stufe F.

**Das ist die einzige Stelle im System mit einer deutschen Uhrzeit** — sie
steht bewusst dort und nicht im Code.

Produktive Anbieter werden ebenfalls dort scharfgeschaltet, über Argumente
(`--earnings-provider`, `--research-provider`), nicht über
`config/default.yaml`. So findet ein `git pull` auf dem Server keinen lokalen
Diff.

Rückgabewerte an die Aufgabenplanung: `0` erledigt oder nichts zu tun, `1`
versucht und gescheitert, `2` Konfigurations- oder Umgebungsfehler, `130`
abgebrochen.

---

## Neustartverhalten

Nach einem Serverneustart sind Anmeldung und TWS-Start **manuell** — die
akzeptierte Einschränkung aus ADR 0018. Bis dahin liefert der Analyzer keine
Daten; der Dispatcher meldet den ausgefallenen Lauf über den
Benachrichtigungskanal, sobald die Nachholfrist abgelaufen ist.

Ein unterbrochener Lauf wird als unterbrochen erkannt und nicht doppelt
gerechnet.

---

## Persistente Daten

- PostgreSQL-Daten,
- Anwendungslogs,
- Konfiguration ohne Geheimnisse.

Geheimnisse liegen ausschließlich in Umgebungsvariablen mit Präfix `ATA_`
([ADR 0005](adr/0005-konfiguration-und-secrets.md)) und werden nirgends
mitgesichert.

## Backup

**Ein Sicherungsverfahren ist noch nicht beschlossen.** Zu sichern sind
Datenbank, Berichte und Konfiguration; wie und wohin, ist offen. ADR 0036
hält das ausdrücklich als offenen Punkt fest, statt hier ein Verfahren zu
behaupten, das niemand eingerichtet hat.
