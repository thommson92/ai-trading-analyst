# ADR 0036: Nativer Windows-Betrieb ist das Deployment des MVP

- Status: Angenommen
- Datum: 2026-08-30

## Kontext

Das System läuft seit der Inbetriebnahme im August 2026 produktiv. Wie es
läuft, steht ausführlich in `docs/14 - Inbetriebnahme und Betrieb.md`: eine
virtuelle Umgebung auf dem Windows-Server, installiert aus der Lock-Datei mit
Hash-Prüfung ([ADR 0008](0008-reproduzierbare-installation.md),
[ADR 0015](0015-plattformunabhaengige-lock-dateien.md)), ein lokales
PostgreSQL, und ein Eintrag in der Windows-Aufgabenplanung, der
`cli dispatch --provider ibkr` auslöst.

Was die Dokumentation *fordert*, ist etwas anderes. `docs/13 - Deployment.md`
und `docs/10 - System Architecture.md` §14 beschreiben Docker Compose mit den
Diensten `frontend`, `backend`, `worker`, `postgres`, `reverse-proxy` und
optional `redis`. Beide Dokumente stammen aus der Planungsphase vor der
ersten Zeile Code.

Der Abstand ist nicht klein:

- Es gibt im gesamten Repository **kein Dockerfile, keine Compose-Datei und
  kein Deployment-Skript.** Die einzige CI-Datei baut und testet, sie liefert
  nicht aus.
- `redis` ist durch [ADR 0006](0006-kein-redis-im-mvp.md) ausgeschlossen;
  koordiniert wird über PostgreSQL.
- Einen `worker`-Dienst gibt es nicht. Der Dispatcher ist ein idempotenter
  Einzelstart, kein Dauerprozess — das ist die Entscheidung aus
  [ADR 0019](0019-trading-day-dispatcher.md).
- Ein `frontend` existiert als Next.js-Gerüst, wird aber nicht ausgeliefert;
  es gehört zu Sprint 6.
- Ein `reverse-proxy` setzt externen Zugriff voraus. Ob und wie das Dashboard
  von außen erreichbar wird, ist unentschieden (F12, Doc 10 §19).

Das Repository-Audit vom 2026-08-23 hat das als einzige **implementierte
Architekturentscheidung ohne Beschlussdokument** benannt: gelebte Praxis, die
nirgends beschlossen wurde, gegen eine Dokumentation, die etwas beschreibt,
das es nicht gibt. Weil Doc 10 bei Widersprüchen maßgeblich ist
([ADR 0001](0001-dokumentenhierarchie.md)), steht heute die maßgebliche
Quelle im Widerspruch zum laufenden Betrieb.

## Entscheidung

**Der native Betrieb auf dem Windows-Server ist das Deployment des MVP.**
Nicht als Zwischenlösung, sondern als beschlossene Zielstruktur für Phase 1.

Festgeschrieben wird damit:

1. **Eine virtuelle Python-Umgebung auf dem Server**, installiert aus
   `requirements-dev.lock.txt` mit `--require-hashes`. Keine Container.
2. **PostgreSQL läuft lokal auf demselben Server**, nicht als Container.
   Migrationen über Alembic, ausgeführt von Hand beim Aktualisieren — es gibt
   keinen zweiten Prozess, der sie parallel anstoßen könnte.
3. **Die Windows-Aufgabenplanung ist der einzige Auslöser.** Sie startet
   `cli dispatch`; der Dispatcher entscheidet selbst, ob heute ein Handelstag
   ist und ob der Lauf schon stattgefunden hat. Der Rückgabewert-Kontrakt
   (0 erledigt oder nichts zu tun, 1 gescheitert, 2 Konfigurationsfehler,
   130 abgebrochen) ist Teil der Schnittstelle zur Aufgabenplanung.
4. **Produktive Anbieter werden über Argumente in der Aufgabenplanung
   scharfgeschaltet**, nicht in `config/default.yaml` — damit ein `git pull`
   auf dem Server keinen lokalen Diff vorfindet.
5. **Kein Redis, kein Worker-Dienst, kein Reverse Proxy, kein
   Frontend-Deployment** im MVP.

Containerisierung wird **nicht verworfen, sondern vertagt**: Sie wird zum
Dashboard-Sprint neu bewertet, wenn mit dem Frontend erstmals etwas entsteht,
das ausgeliefert werden muss und für das ein Reverse Proxy einen Zweck hat.

`docs/13 - Deployment.md` wird neu geschrieben. `docs/10` §14 wird auf den
Ist-Betrieb umgestellt — ein neues Doc 13 allein bliebe wirkungslos, solange
die maßgebliche Quelle weiter Container fordert.

## Begründung

**Die TWS erzwingt es.** Interactive Brokers' Trader Workstation ist eine
Desktop-Anwendung und braucht eine angemeldete Windows-Sitzung
([ADR 0014](0014-ibkr-produktivintegration-freigegeben.md), Einschränkung E2;
[ADR 0018](0018-kein-windows-autologon.md)). Sie ist die Quelle **aller**
Kursdaten. Ein Container könnte sie nicht ersetzen und müsste ohnehin zu
einem Prozess auf dem Host sprechen. Der Gewinn an Kapselung wäre also von
vornherein unvollständig — der wichtigste Teil des Systems bliebe außerhalb.

**Der Nutzen von Compose entsteht hier nicht.** Docker Compose zahlt sich aus,
wo mehrere Dienste zusammenspielen, reproduzierbar hochfahren und voneinander
isoliert sein müssen. Vorhanden ist genau ein Prozess, der einige Minuten am
Tag läuft, und eine Datenbank. Reproduzierbarkeit ist bereits über die
Lock-Datei mit Hash-Prüfung gesichert, und zwar auf einer Ebene, die ein
Basis-Image nicht erreicht.

**Es funktioniert nachweislich.** Der Betrieb ist über die Stufen A bis H
abgenommen, der Tageslauf läuft, der Benachrichtigungskanal steht. Eine
Migration auf Container wäre Aufwand ohne belegten Nutzen und würde einen
funktionierenden Betrieb gegen einen ungetesteten eintauschen.

**Zur Alternative:** Die Docker-Migration jetzt einzuplanen hieße, den
gesamten Betriebsteil neu abzunehmen, bevor auch nur ein Dienst existiert,
der von Containern profitiert. Zum Dashboard-Sprint ist die Frage anders
gestellt und ehrlicher zu beantworten.

## Konsequenzen

**Positiv**

- Die maßgebliche Quelle beschreibt wieder den Betrieb. Wer Doc 10 §14 liest,
  findet, was auf dem Server steht.
- Der Ist-Betrieb ist begründet und nicht nur vorgefunden. Wer ihn ändern
  will, löst dieses ADR ab, statt eine ungeschriebene Praxis umzustellen.
- E6 und M11 aus dem Audit vom 2026-08-23 sind erledigt.

**Negativ und offen**

- **Der Betrieb bleibt an eine Maschine gebunden.** Es gibt keinen zweiten
  Server, auf den sich das Ganze umziehen ließe, ohne die Schritte aus Doc 14
  von Hand zu wiederholen. Das ist der Preis; er wird bewusst gezahlt.
- **Aktualisierungen sind Handarbeit** — `git pull`, gegebenenfalls
  Neuinstallation aus der Lock-Datei, `alembic upgrade head`. Es gibt kein
  Rollback per Image-Tag. Was schiefgeht, wird über Git zurückgenommen.
- **Der Neustartanspruch aus Doc 10 §14 („Container müssen nach einem
  Serverneustart automatisch starten") entfällt in dieser Form.** Nach einem
  Neustart braucht es die manuelle Anmeldung und den TWS-Start — genau die
  Einschränkung, die ADR 0018 bereits akzeptiert hat. Der Anspruch, einen
  unterbrochenen Lauf als unterbrochen zu erkennen, bleibt und wird vom
  Dispatcher erfüllt.
- **Ein Backup-Verfahren ist damit nicht beschlossen.** Doc 13 nennt
  Datenbank, Berichte und Konfiguration als zu sichern; wie gesichert wird,
  bleibt außerhalb dieses ADR und ist weiterhin offen.

### Nachtrag 2026-09-01: die vertagte Container-Frage ist beantwortet

Der Anlass für die Neubewertung ist eingetreten — mit Sprint 6 entsteht das
Frontend, das ausgeliefert werden muss. Das Ergebnis ist dasselbe wie hier:
**kein Container, kein Reverse Proxy.** Das Dashboard wird als statischer
Export gebaut und von derselben FastAPI-Anwendung mit ausgeliefert, die die
API bereitstellt; Node bleibt Bauwerkzeug und wird keine Laufzeit auf dem
Server. Siehe [ADR 0052](0052-dashboard-als-statischer-export.md).

Punkt 5 der Entscheidung — „kein Frontend-Deployment im MVP" — ist damit
überholt: Es gibt eines, und es kostet keinen zweiten Dienst. Neu hinzu kommt
allerdings der **erste Dauerprozess** des Systems (`uvicorn` als
Autostart-Eintrag der Aufgabenplanung), was Punkt 3 nicht aufhebt: Der
Auslöser der Analyse bleibt allein die Aufgabenplanung, und die API kann
keinen Lauf starten ([ADR 0053](0053-lese-api-kein-lauf-ueber-http.md)).

Auch das Backup ist inzwischen beschlossen, außerhalb dieses ADR: Doc 14,
Abschnitt „Sicherung".
