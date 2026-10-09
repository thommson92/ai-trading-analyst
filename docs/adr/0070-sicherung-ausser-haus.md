# ADR 0070: Die Sicherung verlässt den Server — verschlüsselt, schreibend, versioniert

- Status: Vorgeschlagen
- Datum: 2026-09-22
- Anbieter entschieden am 2026-10-09 — siehe den Nachtrag am Ende
- Löst ab: die Klausel „Neu zu bewerten nach stabilem Betrieb" in
  [Doc 10 §15](../10%20-%20System%20Architecture.md) und in
  [Doc 14](../14%20-%20Inbetriebnahme%20und%20Betrieb.md), Abschnitt „Sicherung"

## Kontext

[Doc 10 §15](../10%20-%20System%20Architecture.md) nennt fünf
Mindestanforderungen an die Datensicherung. Vier sind beschrieben und
umgesetzt: tägliches Backup, definierte Aufbewahrungsfrist, regelmäßiger
Restore-Test und — seit dem 2026-09-22 — ein dokumentierter
Wiederherstellungsprozess. **Die fünfte ist offen:** „Sicherung außerhalb des
primären Datenvolumes."

Der Beschluss vom 2026-09-01 hat das bewusst zurückgestellt: *„Neu zu
bewerten nach stabilem Betrieb."* Diese Bedingung ist erfüllt. Seither sind
rund vier Wochen produktiver Betrieb aufgelaufen, und mit ihnen ein Bestand,
der sich nicht wiederbeschaffen lässt.

Der Audit vom 2026-09-20 führt den Zustand als **AUDIT-003-006** (High) und
die fehlende Sicherung überhaupt als **AUDIT-003-002** (Critical). Der
entscheidende Satz steht in
[ADR 0058](0058-optionsvorschlaege-im-rueckblick.md), Festlegung 1: die
Optionsnotierungen sind *„rund 400 echte Notierungen je Handelstag, die es
nie wieder geben wird"*. Historische Optionskurse sind nicht rückwirkend
abrufbar. Dasselbe gilt für jede gespeicherte Analyse: Sie ist eine
Momentaufnahme mit Versionsstempel, und eine Neuberechnung von heute ist
nicht dasselbe Ergebnis.

Eine Sicherung auf demselben Rechner schützt gegen Softwarefehler,
Fehlbedienung und eine kaputte Migration. Sie schützt **nicht** gegen den
Ausfall der Platte, den Verlust des Rechners und — der eigentliche Punkt —
nicht gegen einen Verschlüsselungstrojaner: Der verschlüsselt, was das
Benutzerkonto beschreiben darf, und das schließt `D:\backups\ata` ein. Der
Zustand danach ist derselbe wie ganz ohne Sicherung.

## Entscheidung

### 1. Das Ziel ist ein S3-kompatibler Objektspeicher

Nicht ein Netzlaufwerk, nicht ein Wechselmedium.

Gegen das **Netzlaufwerk** spricht, dass der Server hineinschreiben können
muss — und damit erreicht es derselbe Trojaner. Ein Pull-Verfahren, bei dem
ein NAS sich die Dumps selbst abholt, löste das, verlagert die Einrichtung
aber auf ein zweites Gerät mit eigener Pflege.

Gegen das **Wechselmedium** spricht nichts Technisches — physisch getrennt
ist der beste Schutz überhaupt. Es verlangt aber einen wiederkehrenden
Handgriff, und ein Verfahren, das an einen vergessenen Plattentausch hängt,
schläft still ein. Dieses Projekt hat bereits einen Befund dieser Art
(AUDIT-003-002: das Verfahren war beschrieben und nie eingerichtet).

Der Anbieter bleibt offen und ist keine Architekturentscheidung: Backblaze
B2, Cloudflare R2 und AWS S3 erfüllen die Anforderungen aus 2. und 4.
gleichermaßen. Cloudflare R2 hat den praktischen Vorzug, dass das Projekt
dort bereits ein Konto führt ([ADR 0060](0060-dashboard-ausserhalb-des-servers.md)).

### 2. Der Server darf schreiben, nicht löschen

Die Zugangsdaten auf dem Server tragen **ausschließlich** das Recht, neue
Objekte anzulegen. Kein Löschen, kein Überschreiben. Dazu die Versionierung
des Buckets und, wo der Anbieter es anbietet, eine Aufbewahrungssperre
(Object Lock) über die Aufbewahrungsfrist.

**Das ist der eigentliche Hebel, nicht die Entfernung.** Ein Ziel, das der
Server löschen darf, ist bei einem kompromittierten Server verloren,
gleichgültig wie weit weg es steht.

### 3. Verschlüsselt wird auf dem Server, gegen einen öffentlichen Schlüssel

Der Dump wird verschlüsselt, **bevor** er den Server verlässt. Verwendet wird
`age` mit einem **Empfängerschlüsselpaar**: Auf dem Server liegt nur der
öffentliche Schlüssel, der private liegt im Passwortmanager.

Damit kann ein Angreifer, der den Server vollständig übernimmt, die
ausgelagerten Sicherungen weder lesen noch entschlüsseln — er findet einen
Schlüssel vor, mit dem sich nur verschlüsseln lässt. Eine Passphrase auf dem
Server hätte diese Eigenschaft nicht.

Das Verfahren ist dasselbe Denken wie beim Dashboard-Export
([ADR 0060](0060-dashboard-ausserhalb-des-servers.md)): Der Ort, der die
Daten hält, kann sie nicht lesen.

### 4. Extern länger aufbewahrt als lokal

Lokal bleiben es vierzehn Tage. Extern **90 Tage**.

Die beiden Fristen beantworten verschiedene Fragen. Die lokale deckt den
Fall „gestern ging etwas kaputt" — da zählt Geschwindigkeit, und der Ordner
soll nicht wachsen. Die externe deckt den Fall „vor zwei Monaten ging etwas
kaputt, und es ist erst jetzt aufgefallen" — der Hauptfall, gegen den
Versionierung überhaupt hilft.

### 5. Ein Glied der Sicherungskette, kein zweiter Task

Die Kette lautet: **Dump → Lesbarkeitsprüfung → Verschlüsseln → Hochladen →
Aufräumen.** Sie läuft in `scripts/sicherung.ps1`, ausgelöst durch einen
neuen Parameter `-ExternesZiel`; ohne ihn verhält sich das Skript
unverändert.

Hochgeladen wird **nur, was `pg_restore --list` bereits als lesbar bestätigt
hat.** Eine abgebrochene Datei außer Haus zu tragen wäre schlimmer als keine:
Sie sähe wie eine Sicherung aus.

Scheitert der Upload, endet das Skript mit Rückgabewert 2, und **das
Aufräumen unterbleibt**. Der lokale Dump ist dann trotzdem da — aber der
Zustand „gesichert, aber nur hier" ist genau der, den dieses ADR beendet,
und er soll deshalb sichtbar sein.

## Begründung

**Zu 1.** Die drei Optionen unterscheiden sich weniger in der Entfernung als
in der Frage, wer löschen darf und wer daran denken muss. Der Objektspeicher
ist die einzige, die ohne wiederkehrenden Handgriff auskommt **und** das
Löschrecht sauber trennen kann.

**Zu 2.** Die Bedrohung, gegen die ein Offsite-Backup wirklich hilft, ist
nicht die kaputte Platte — dagegen hülfe schon ein zweites Laufwerk. Es ist
der Angreifer mit den Rechten des Benutzerkontos. Gegen den wirkt
ausschließlich, dass die Kopie nicht löschbar ist.

**Zu 3.** `age` statt GnuPG: ein einzelnes statisches Programm ohne
Schlüsselbund, ohne Konfiguration und mit genau einem Verwendungszweck.
GnuPG kann mehr, und jedes Mehr ist hier eine Fehlerquelle in einem Skript,
das nachts unbeaufsichtigt läuft. Gegen eine reine Passphrase spricht 2.:
Sie läge auf dem Server.

**Zu 4.** Neunzig Tage decken einen Quartalsturnus ab (Doc 14, „Pflege") —
ein Fehler, der beim Pflegetermin auffällt, ist damit noch reparabel.

**Zu 5.** Die Reihenfolge ist dieselbe wie im bestehenden Skript und aus
demselben Grund: Erst das Neue sichern und prüfen, dann das Alte wegräumen.
Ein eigener Task um 00:15 wäre der offensichtliche Gegenentwurf; er bräuchte
aber eine Zeitabhängigkeit zu einem Vorgang, dessen Dauer nicht feststeht,
und könnte eine noch gar nicht fertige Sicherung vorfinden. Eine Kette mit
echten Abhängigkeiten gehört in einen Vorgang.

## Konsequenzen

**Positiv**

- Die letzte der fünf Mindestanforderungen aus Doc 10 §15 ist erfüllt.
- Ein vollständig kompromittierter Server kostet höchstens den Bestand seit
  der letzten Sicherung — nicht den gesamten Bestand.
- Die ausgelagerten Sicherungen sind auch für den Anbieter unlesbar.
- Das Aufbewahrungsziel aus Doc 10 §15 („maximal ein Handelstag
  Datenverlust") gilt damit erstmals auch gegen den Verlust des Rechners.

**Negativ und offen**

- **Ein neuer Schlüssel, der verloren gehen kann.** Geht der private
  `age`-Schlüssel verloren, sind alle externen Sicherungen wertlos. Er gehört
  in den Passwortmanager, zusammen mit
  `ATA_DASHBOARD_EXPORT_PASSPHRASE`, und auf die Notfallkarte aus Stufe L.
- **Eine neue Abhängigkeit** (`age`) und ein neuer Anbieterzugang mit eigener
  Pflege — Tokenablauf gehört auf die Liste des Pflegetermins.
- **Laufende Kosten**, wenn auch geringe: Ein Dump dieser Datenbank liegt
  derzeit im niedrigen dreistelligen Megabytebereich, neunzig Tage davon im
  einstelligen Gigabytebereich.
- **Der Anbieter ist nicht entschieden.** Punkt 1 nennt die Kriterien und
  eine naheliegende Wahl, trifft sie aber nicht. Das gehört in die Umsetzung,
  zusammen mit der Frage, ob der bestehende Cloudflare-Zugang dafür verwendet
  oder ein getrennter angelegt wird — getrennt wäre sauberer, weil der
  Dashboard-Token heute Schreibrechte auf einen öffentlich erreichbaren
  Worker hat.
- **Nicht gelöst: der Restore-Test der externen Kopie.** Die Zählprobe läuft
  gegen die lokale. Ob die hochgeladene Datei wieder herunterkommt und sich
  entschlüsseln lässt, gehört einmal je Pflegetermin geprüft — sonst
  entsteht genau die Art Vertrauen, die dieses Projekt an anderer Stelle
  schon einmal enttäuscht hat.

## Nachtrag vom 2026-10-09: der Anbieter ist AWS S3

Punkt 1 hat die Wahl offen gelassen und drei gleichwertige Anbieter genannt.
Der Inhaber hat **AWS S3** gewählt, weil dort bereits ein Konto besteht.

Damit löst sich die Frage aus den Konsequenzen („ob der bestehende
Cloudflare-Zugang verwendet oder ein getrennter angelegt wird") von selbst:
Der Zugang ist schon durch den Anbieterwechsel getrennt. Der
Dashboard-Token von [ADR 0060](0060-dashboard-ausserhalb-des-servers.md)
bekommt keine Rechte an den Sicherungen, und der Sicherungsschlüssel keine am
Worker.

### Was aus Punkt 2 konkret wird

Punkt 2 verlangt „schreiben, nicht löschen". Bei AWS S3 sind das drei
Einstellungen, die zusammen wirken müssen — eine allein genügt nicht:

| Einstellung | Wirkung |
|---|---|
| Versionierung am Bucket | Voraussetzung für alles Weitere; ohne sie gibt es kein Object Lock |
| Object Lock, Vorgabe **90 Tage** | Ein hochgeladenes Objekt ist bis dahin unveränderlich — auch für den, der es hochgeladen hat |
| IAM-Richtlinie: nur `s3:PutObject` | Der Server kann anlegen. Nicht lesen, nicht löschen, nicht die Aufbewahrung verkürzen |

Die Aufbewahrungsfrist aus Punkt 4 steht damit **am Bucket** und nicht im
Skript. Das ist der Unterschied, auf den es ankommt: Eine Frist im Skript
kann der ändern, der das Skript ändern kann.

### Object Lock im Modus GOVERNANCE, nicht COMPLIANCE

S3 kennt zwei Modi. `COMPLIANCE` kann **niemand** aufheben, auch nicht das
Root-Konto. `GOVERNANCE` kann aufheben, wer das Recht
`s3:BypassGovernanceRetention` besitzt.

Gewählt wird `GOVERNANCE`, und zwar nicht aus Bequemlichkeit, sondern weil
es gegen die Bedrohung aus Punkt 2 **genauso** wirkt: Der Angreifer hat die
Zugangsdaten des Servers, und die tragen dieses Recht nicht. Er findet einen
Zugang vor, mit dem sich nur anlegen lässt — unabhängig vom Modus.

Was `COMPLIANCE` zusätzlich abdeckt, ist der Fall, dass das
AWS-Administrationskonto selbst übernommen wird. Was es kostet, ist die
Unumkehrbarkeit jeder Fehlkonfiguration: Ein versehentlich hochgeladenes
Objekt ist neunzig Tage lang unlöschbar und wird neunzig Tage lang bezahlt.
Bei einem Verfahren, das gerade erst eingerichtet wird, ist die
Fehlkonfiguration der wahrscheinlichere Fall.

**Das ist eine Abwägung, keine Rechnung** — wer das Administrationskonto für
den gefährdeteren Punkt hält, nimmt `COMPLIANCE` und muss am Bucket nichts
weiter ändern als diesen einen Wert.

### Die Lebenszyklusregel löscht, nicht der Server

Punkt 4 nennt 90 Tage extern. Gelöscht wird durch eine Lifecycle-Regel am
Bucket, nicht durch das Skript — der Server hat dieses Recht ja gerade
nicht.

Die Regel läuft bei **100 Tagen**, nicht bei 90. Object Lock verweigert die
Löschung, solange die Aufbewahrung greift, und eine Regel, die auf den Tag
genau mit ihr zusammenfällt, scheitert bei jedem Lauf einmal, bevor sie
greift. Zehn Tage Abstand sind billiger als eine Regel, die
Fehlermeldungen erzeugt, die niemand liest.

### Zwei neue Werkzeuge auf dem Server

`age` für Punkt 3 und die **AWS CLI v2** für den Upload. Beide als
Parameter des Skripts hinterlegbar, nach dem Vorbild von `-PgBin` — damit
hängt das Verfahren nicht am Suchpfad eines Dienstkontos.

Die AWS CLI spricht S3 über `--endpoint-url` auch mit anderen Anbietern. Die
Wahl aus diesem Nachtrag ist damit umkehrbar, ohne das Skript anzufassen;
Punkt 1 bleibt der Beschluss, dieser Nachtrag nur seine Ausführung.

### Was offen bleibt

Die Zählprobe der **externen** Kopie, aus den Konsequenzen oben. Sie bekommt
mit `scripts/sicherung-extern-probe.ps1` ein eigenes Skript und einen Platz
im Pflegetermin (Doc 14). Sie läuft **nicht** täglich: Sie braucht den
privaten Schlüssel, und der soll nicht auf dem Server liegen.
