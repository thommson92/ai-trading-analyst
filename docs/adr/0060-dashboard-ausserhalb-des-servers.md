# ADR 0060: Das Dashboard läuft außerhalb des Servers — Snapshot je Lauf, ausgehend hochgeladen, Anmeldung an der Kante, Zero-Knowledge als Zielstufe

- Status: **Angenommen am 2026-09-17** (vorgeschlagen am 2026-09-06; die
  sieben Entscheidungspunkte am 2026-09-07 beschieden, der Proof of
  Concept beim Anbieter am 2026-09-17 abgeschlossen — siehe den Nachtrag
  am Ende und Doc 14, Stufe L)
- Datum: 2026-09-06

## Kontext

[ADR 0049](0049-dashboard-mvp-nur-lan.md) hat den externen Zugriff auf das
Dashboard (F12) für das MVP verneint und die Neubewertung nach stabilem
Betrieb angekündigt. Der Tageslauf läuft seit dem 2026-09-01 automatisch.
Ein erster Spike vom 2026-09-06 hat den **Zugang zum Server** untersucht —
privater Fernzugang über ein identitätsgebundenes Overlay-Netz — und ist
mit [ADR 0059](0059-fernzugang-dashboard-overlay-netz.md) (Vorgeschlagen)
**zurückgestellt**: Der Weg
verlangt Client-Software auf jedem Gerät, und der Inhaber will von
beliebigen Geräten aus zugreifen, mit einer einfachen Anmeldung. Der
Zugriff auf das Dashboard gilt ihm als nicht sicherheitskritisch; der
Server soll durch das Dashboard nicht erreichbar werden.

Dieses ADR beantwortet F12 deshalb umgekehrt: **Nicht der Nutzer kommt zum
Server, die Ergebnisse gehen zum Nutzer.** Grundlage ist der Spike-Bericht
[docs/requirements/f12-externes-hosting-spike.md](../requirements/f12-externes-hosting-spike.md);
die Vorgaben des Inhabers stehen dort in Abschnitt 3.1.

Was den Rahmen setzt:

- **Das Dashboard ist bereits ein statischer Export** ohne Geschäftslogik
  ([ADR 0052](0052-dashboard-als-statischer-export.md)); seine Daten kommen
  aus elf lesenden Endpunkten ([ADR 0053](0053-lese-api-kein-lauf-ueber-http.md)),
  deren Antworten sich als Dateien ablegen lassen. Der Chart-Payload einer
  Aktie ist gemessen 141 Byte je Kerze, hochgerechnet auf fünf Jahre rund
  350 KB roh; der Vollexport aller Ansichten liegt geschätzt bei rund 75 MB
  roh und 17 MB komprimiert.
- **Der Server spricht bereits ausgehend mit vier Diensten** (Finnhub,
  EDGAR, Anthropic, Telegram), mit Tokens aus `ATA_`-Variablen und
  Fehlerisolation am Laufende ([ADR 0024](0024-benachrichtigungskanal-telegram.md)).
  Ein Upload nach dem Lauf fügt sich in dieses Muster.
- **Der Server ist der Handelsrechner** (TWS mit Orderrecht) und bleibt
  ohne eingehende Freigabe — das ist die Bedingung, unter der ADR 0049
  ohne Authentifizierung auskam, und sie bleibt hier unberührt.
- **Genau ein Nutzer.** Finnhubs L8 ([ADR 0017](0017-finnhub-fuer-earnings-und-ratings.md))
  und das Deployment-Gate aus [ADR 0022](0022-research-agent-quellen.md)
  stellen sich mit einem Hosting-Anbieter neu: nicht als Frage nach
  fremden Lesern, sondern nach dem Anbieter als Dritten.
- **Das Repository ist öffentlich** ([ADR 0031](0031-merge-schutz-aktiv.md)):
  Hostnamen, Projektnamen und Konten gehören in kein Dokument und keinen
  Workflow.

Untersucht wurden: ein statischer Export bei einem Anbieter mit Anmeldung
an der Kante, ein eigener kleiner Server mit Reverse Proxy, ein
Zero-Knowledge-Export (auf dem Server verschlüsselt, im Browser
entschlüsselt) allein und hinter der Kantenanmeldung, eine gehostete API
mit Datenbankkopie, sowie Datenwege und Bauweisen — Spike-Bericht,
Abschnitte 6 und 7.

## Entscheidung

1. **Der Server bleibt unerreichbar.** Kein eingehender Port, kein Agent,
   kein Tunnel. Die einzige neue Verbindung geht vom Server nach außen:
   ein HTTPS-Upload mit einem Token, das beim Anbieter **auf Schreiben**
   und — wo der Anbieter Projekt-Granularität bietet — **auf genau diese
   Seite** beschränkt ist; bietet er sie nicht, gehört die Seite in ein
   eigenes Konto nur für diesen Zweck.
2. **Nach jedem Lauf verlässt ein Snapshot den Server.** Ein Exportschritt
   am Ende von `RunAnalysisUseCase.execute()` — Port `DashboardPublisher`
   neben `Notifier`, Adapter in der Infrastruktur, **dieselbe
   Fehlerisolation wie die Telegram-Meldung**: Ein fehlgeschlagener Upload
   wird protokolliert und über Telegram gemeldet, der Lauf gilt trotzdem als
   erledigt. Dazu `cli publish` für Handbetrieb und Vollexport. Geschaltet
   wird über ein Argument der Aufgabenplanung; die ausgelieferte
   Konfiguration steht auf `none` ([ADR 0036](0036-nativer-windows-betrieb.md),
   Punkt 4).
3. **Der Snapshot ist ein Datenbaum aus den Antworten der API**, erzeugt
   von denselben Anwendungsfällen und Antwortschemata — keine zweite
   Rechnung, kein zweiter Zuschnitt —, mit einem **Manifest** (Zeitpunkt,
   Lauf-ID, Export-Kennung, Versionen). Die Oberfläche zeigt den Stand aus
   dem Manifest an jeder Ansicht: Ein alter Stand muss alt aussehen.
4. **Die Oberfläche bekommt einen statischen Datenmodus.** Dasselbe
   Frontend, gebaut mit einer Umgebungsvariablen, holt seine Antworten aus
   dem Datenbaum statt von der API; Paginierung und Filter der Läufe
   geschehen im Browser. Der Server baut diese Fassung wie heute die
   LAN-Fassung (Node als Werkzeug, ADR 0052) und lädt Oberfläche und
   Datenbaum als **ein** Deployment hoch. Das LAN-Dashboard auf dem Server
   bleibt bestehen.
5. **Außerhalb liegt eine statische Seite hinter der Anmeldung des
   Anbieters** (beispielhaft: Cloudflare Pages mit Access, Azure Static
   Web Apps). Die Zugriffsregel deckt den **ganzen Hostnamen** ab —
   jede Datei, auch Vorschau-, Zweig- und ältere Deployment-Adressen, auch
   die Standard-Subdomain neben einem eigenen Namen —, erlaubt **genau
   einen Nutzer** und verlangt MFA über ein Identitätsanbieter-Konto mit
   Authenticator-App oder Passkey; ein E-Mail-Einmalcode ist nur Rückfall.
   Sitzung kurz (Vorschlag 24 Stunden), Cookies `Secure`, `HttpOnly`,
   `SameSite`, `noindex`, nichtssagende Namen. Bevorzugt wird ein
   Anbieter, dessen Zugriffsregel **außerhalb des Deployments** liegt —
   sonst hebt ein Token-Dieb sie mit dem nächsten Upload auf — und der
   **alte Deployments löschen** lässt, weil seine Historie sonst jeden
   Snapshot aufbewahrt. Kein eigenes Anmeldeformular, kein eigener
   Sitzungscode; `ATA_SESSION_SECRET` bleibt reserviert.
6. **Zero-Knowledge ist die Zielstufe, nicht ein Extra.** In Stufe 2 wird
   der Datenbaum auf dem Server verschlüsselt — Schlüssel aus einer
   Passphrase abgeleitet (PBKDF2-HMAC-SHA256, mindestens 600.000
   Iterationen, zufälliges Salt je Export in einem kleinen Klartextkopf,
   dessen Mindestwerte der Browser erzwingt), je Datei AES-256-GCM mit
   zufälliger Nonce und **Export-Kennung und Dateipfad als Zusatzdaten**,
   komprimiert und auf Größenklassen aufgefüllt vor dem Verschlüsseln,
   **opake Dateinamen**, das Manifest selbst verschlüsselt — und im Browser
   mit WebCrypto entschlüsselt, in einem **eigenen Build, der Klartext gar
   nicht annimmt**: Das Verfahren ist Eigenschaft des Builds, nicht des
   Manifests, damit niemand mit Schreibzugriff auf Klartext zurückschalten
   kann. Der Anbieter sieht Chiffrat, Dateizahl und Größenklassen;
   gefälschte, vertauschte und veraltete Datendateien werden verworfen; die
   Passphrase im Passwortmanager ist die „einfache Anmeldung", die
   Kantenanmeldung bleibt als MFA davor. Stufe 1 wird so gebaut, dass
   Stufe 2 eine Schreib- und eine Ladefunktion austauscht und den Build
   umschaltet. Die Verschlüsselung braucht eine neue Abhängigkeit
   (`cryptography`), Testvektoren und eine unabhängige Review des
   Kryptocodes. **Ob Stufe 2 unmittelbar folgt, ist Entscheidungspunkt E1
   des Spike-Berichts; empfohlen ist unmittelbar.**
7. **Außerhalb gibt es keine API, keine Datenbank, keinen Schreibpfad und
   keinen Weg zurück zum Server.** Die Trennung zwischen lesender Anzeige
   und transaktionalen Funktionen ist Bauart, nicht Regel. Eine
   schreibende Funktion wäre ein anderes System und ein neues ADR.
8. **Geheimnisse:** `ATA_DASHBOARD_PUBLISH_TOKEN` und in Stufe 2
   `ATA_DASHBOARD_EXPORT_PASSPHRASE` in `Secrets` (Schwärzung nach
   [ADR 0044](0044-geheimnisse-an-der-log-senke-schwaerzen.md)); Rotation
   jährlich und bei Verdacht. Hostname, Projektname und Konto stehen in
   keinem Dokument und keinem Workflow des Repositories.
9. **Der Notausschalter** hat fünf Ebenen (Spike-Bericht, Abschnitt 12):
   Seite oder Regel beim Anbieter abschalten (samt alter Deployments),
   Token widerrufen, Exportschritt abschalten, Passphrase wechseln und alte
   Fassungen löschen, Sitzungen beenden. Er hält den Tageslauf nicht an und
   löscht nichts auf dem Server.
10. **Erst ein Proof of Concept, dann der Betrieb.** Der PoC läuft mit
    synthetischen Daten (erzeugte Golden-Master-Fälle, Fixture-Anbieter,
    eigene Datenbank), einem Wegwerf-Skript statt Produktcode, einem
    schreibbeschränkten Token und vollständigem Rückbau; er weist nach,
    dass ohne Anmeldung keine Datei erreichbar ist — auch keine ältere
    Fassung —, dass das Token nichts anderes kann, dass in Stufe 2 ein auf
    Klartext gesetzter Kopf, eine veraltete Datei und eine vertauschte
    Datei verworfen werden, und dass der Server unverändert bleibt
    (Spike-Bericht, Abschnitt 11). Dieses ADR wird erst nach bestandenem
    PoC angenommen.
11. **Was nicht entschieden wird:** die Anbieterwahl (PoC, mit
    Nutzungsbedingungen); ein Link in der Telegram-Meldung (der Nachtrag
    zu [ADR 0040](0040-inhalt-der-ergebnismeldung.md) bindet die Frage an
    diese Neubewertung — sie wird mit Stufe 2 entschieden,
    Entscheidungspunkt E5); die Zukunft von ADR 0059 für die Fernwartung
    des Servers (E7).

## Begründung

**Dateien hinter einer Anmeldung sind die kleinste Angriffsfläche, die
ein Dashboard außerhalb des Servers haben kann.** Kein Prozess draußen
rechnet, keine API nimmt Anfragen entgegen, keine Datenbank hält
Zugangsdaten. Was der Anbieter ausliefert, hat der Server erzeugt; was
ein Angreifer draußen findet, ist entweder die Anmeldeseite des Anbieters
— gebaut für Credential Stuffing und Ratenbegrenzung — oder, in Stufe 2,
Chiffrat.

**Der Server bleibt, was ADR 0049 wollte: unerreichbar.** Der Weg dreht
die Richtung um. Der zurückgestellte Overlay-Weg (ADR 0059) ist für den
Zugang **zum Server** die sicherere Antwort — kein öffentlicher Endpunkt,
Ende-zu-Ende, gerätegebunden —, aber er beantwortet eine andere Frage. Für
„beliebige Geräte, einfache Anmeldung" verlangt er genau das, was der
Inhaber ausschließt: Client-Software auf jedem Gerät. Beide Wege schließen
sich nicht aus; dieser hier braucht den anderen nicht.

**Warum Zero-Knowledge die Zielstufe ist und nicht ein Extra:** Stufe 1
allein legt Berichte mit Modelltext, Optionsvorschläge, Kursreihen und
damit die Watchlist im Klartext zu einem Anbieter. Das ist die Lage, die
ADR 0049 mit „solange nichts das eigene Netz verlässt" vermieden hat, und
sie stellt Finnhubs L8 und das Deployment-Gate aus ADR 0022 neu. Stufe 2
verringert beides erheblich: Ein Anbieter, der Chiffrat hält, liest keine
Inhalte — Dateizahl und Größenklassen bleiben ihm; ob das eine „Weitergabe"
ist, bleibt die Einordnung des Inhabers (Spike-Bericht, O1). Und sie
sichert die **Daten** gegen Fälschung, Vertauschung und Replay — eine
Datei, die nicht mit dem Schlüssel, unter ihrem Pfad und für diesen Export
verschlüsselt wurde, verwirft der Browser; das Manifest ist selbst
verschlüsselt, und der Zero-Knowledge-Build nimmt Klartext nicht an. Was
sie nicht sichert, ist die **Oberfläche**: Wer den Host kontrolliert, kann
die Seite ersetzen, die die Passphrase abfragt. Dagegen
steht die Telegram-Meldung als unabhängige Gegenprobe (Symbole,
Signalzahl, Scores, Stufe, bester Put-Vorschlag —
[ADR 0047](0047-scores-in-der-ergebnismeldung.md),
[ADR 0055](0055-put-vorschlag-und-signalzahl-in-der-ergebnismeldung.md);
Kursreihen und Berichtstext deckt sie nicht) und das Deployment-Protokoll
des Anbieters. Diese Grenze ist benannt, nicht
verschwiegen.

**Warum die Anmeldung an der Kante trotz Zero-Knowledge bleibt:** Ohne sie
wäre das Chiffrat öffentlich und die Passphrase der einzige Schutz — ohne
MFA, ohne Ratenbegrenzung, ohne Anmeldeprotokoll. Mit ihr müssen zwei
unabhängige Schichten fallen, bevor jemand Inhalt sieht.

**Warum kein eigener Server draußen:** Er tauschte „nichts zu patchen"
gegen Linux, Proxy und selbst betriebene Anmeldung, für monatliche Kosten
und ohne Zero-Knowledge. **Warum keine gehostete API:** Sie kaufte eine
Aktualität, die der Inhaber nicht verlangt, mit der größten Angriffsfläche
aller Varianten.

**Warum der Server baut und hochlädt, nicht die CI:** Ein Werkzeug, ein
Weg, eine Schreibstelle beim Anbieter. Zwei Schreibstellen — die CI für die
Oberfläche, der Server für die Daten — verdoppeln die Stellen, an denen die
Zugriffsregel vergessen werden kann, und tragen Projektnamen und Token in
die Geheimnisse eines öffentlichen Repositories.

**Warum Isolation wie bei der Meldung:** Das Ergebnis steht in der
Datenbank, bevor der Upload beginnt. Ein Anbieter, der gerade nicht
antwortet, darf keinen Lauf scheitern lassen — dieselbe Regel wie
ADR 0024, aus demselben Grund.

## Konsequenzen

**Positiv**

- Der Server wird durch das Dashboard nicht erreichbarer. Von außen
  antwortet er auf nichts.
- Jedes Gerät mit Browser; kein Client, nichts zu installieren.
- Außerhalb nichts zu patchen; kostenlose Stufen vorhanden; ein
  Anbieterwechsel ist ein Konto, ein Token und ein Vollexport — Stunden.
- Ein Ausfall des Anbieters kostet die Anzeige, nicht den Tageslauf; die
  Telegram-Meldung bleibt.
- Mit Stufe 2 sind die Inhalte gegenüber dem Anbieter verschlossen und
  die Daten gegen Fälschung, Vertauschung und Replay gesichert — Dateizahl
  und Größenklassen bleiben sichtbar, die Oberfläche bleibt Vertrauenssache
  des Hosts.

**Negativ und offen**

- **Stufe 1 legt Klartext zu einem Anbieter.** Die Lizenzfrage (Finnhub
  L8, ADR 0022, IBKR-Bedingungen) ist bis Stufe 2 vom Inhaber zu
  bescheiden — Spike-Bericht, offene Frage O1.
- **Die Anzeige hängt an Host und Token.** Wer eines von beiden hat, kann
  die Seite ersetzen; Stufe 2 schützt die Daten, nicht die Oberfläche.
- **Anwendungsänderungen sind Voraussetzung:** Exporter mit Port, Adapter
  und CLI-Befehl; statischer Datenmodus der Oberfläche; Manifest-Anzeige;
  in Stufe 2 Verschlüsselung auf beiden Seiten mit neuer Abhängigkeit und
  Review. Tage, nicht Stunden — und ein Prototyp im PoC, der nicht gemergt
  wird.
- **Ein Upload-Werkzeug des Anbieters** auf dem Handelsrechner ist
  wahrscheinlich (Datenweg DW2): Die Beispielanbieter kapseln den Upload
  nach Kenntnisstand in Node-Werkzeuge. Dann bekommt ADR 0052 einen
  Nachtrag zu Punkt 2 („Node auch als Auslieferungswerkzeug"). Der Upload
  aus Python (DW1) bleibt der schmalere Weg, wo eine Schnittstelle ihn
  trägt.
- **Die Deployment-Historie des Anbieters ist eine Datenhalde.** Alte
  Fassungen sind zu löschen; ein Anbieter ohne Löschmöglichkeit scheidet
  aus. Ein Passphrase-Wechsel macht alte Chiffrate nicht unlesbar.
- **ADR 0059 liegt seit dem 2026-09-07 in `dev`** — als „Vorgeschlagen,
  zurückgestellt", damit die Nummerierung lückenlos bleibt. Sein
  Zurückstellungs-Nachtrag und Abschnitt 15 seines Spike-Berichts halten
  fest, was dort weitergilt und wo jemand wieder einsteigt.
- **Der Export wächst** mit den Berichten; nur Neues wird hochgeladen, eine
  Archivgrenze ist eine spätere Entscheidung.
- **Zwei Anmeldeschritte in Stufe 2** (Anbieter, dann Passphrase); der
  Passwortmanager füllt die zweite.
- **Dokumentation, die nachzuziehen ist:** Doc 14 (neue Stufe K:
  Exportschritt, Anbieterkonsole, Notfallkarte), Doc 13, Doc 10 §3, §6.15,
  §13, §14, Doc 11 (der Datenbaum als zweiter Vertrag derselben
  Antwortschemata), gegebenenfalls ein Nachtrag zu ADR 0052 Punkt 2, README.

**Was dieses ADR ablöst, sobald es angenommen ist:** die Aussage „keine
Exposition, keine eigene Authentifizierung" aus ADR 0049 wird zu „der
Server bleibt ohne Exposition; das Dashboard läuft zusätzlich außerhalb,
hinter der Anmeldung des Anbieters". ADR 0052 bleibt für die
LAN-Auslieferung in Kraft und bekommt mit dem statischen Datenmodus eine
zweite Auslieferung; ADR 0053 bleibt unverändert — außerhalb gibt es
keine API. ADR 0059 wird für das Dashboard nicht weiterverfolgt; ob es für
die Fernwartung des Servers wieder aufgenommen wird, ist eine eigene
Frage. ADR 0049 wird nicht rückwirkend geändert.

---

## Nachtrag vom 2026-09-07 — die Entscheidungen des Inhabers liegen vor

Der Inhaber hat am 2026-09-07 alle sieben Entscheidungspunkte des
Spike-Berichts (Abschnitt 10.2) beschieden, jeweils der Empfehlung
folgend, und zwei offene Fragen beantwortet. Der Status dieses ADR bleibt
**Vorgeschlagen**: Entscheidung Punkt 10 bindet die Annahme an einen
bestandenen Proof of Concept, und dessen Teil beim Anbieter steht noch aus.

| # | Entschieden |
|---|---|
| E1 | Zero-Knowledge (Stufe 2) wird **unmittelbar** nach Stufe 1 gebaut, nicht offengelassen |
| E2 | Anmeldung an der Kante über einen **Identitätsanbieter** mit Authenticator-App oder Passkey; E-Mail-Einmalcode nur Rückfall |
| E3 | Bauweise **B1** — der Server baut die Oberfläche und lädt beides hoch |
| E4 | Datenweg nach Befund des PoC; mit der Antwort auf O4 ist **DW2** wahrscheinlich |
| E5 | Ein Link in der Telegram-Meldung **erst nach Stufe 2**, dann ja |
| E6 | **Subdomain des Anbieters** mit nichtssagendem Namen, kein eigener Domainname |
| E7 | ADR 0059 bleibt für die **Fernwartung des Servers offen**; für das Dashboard wird er nicht weiterverfolgt |

Beantwortete offene Fragen:

- **O4:** Auf dem Server ist **Node vorhanden**. Damit ist der Datenweg DW2
  — das Werkzeug des Anbieters als Unterprozess — gangbar, ohne dass ein
  neues Laufzeitsystem auf den Handelsrechner käme. Der Nachtrag zu
  [ADR 0052](0052-dashboard-als-statischer-export.md) Punkt 2 wird damit
  wahrscheinlich und ist mit der Anbieterwahl fällig. DW1 (`httpx`) bleibt
  der schmalere Weg und wird bevorzugt, wo der Anbieter eine tragfähige
  HTTP-Schnittstelle bietet.
- **O8:** Der Inhaber hat einen **Passwortmanager auf allen Geräten**, mit
  denen er zugreifen will. Die Passphrase für Stufe 2 wird deshalb **lang
  und zufällig erzeugt** und nirgends getippt oder auswendig gelernt. Das
  ist die stärkere von beiden Varianten; die Ableitungsparameter bleiben
  davon unberührt, weil sie den Fall eines gestohlenen Chiffrats abdecken
  müssen und nicht den einer schwachen Passphrase.

**Eine bewusste Abweichung von Entscheidung Punkt 10.** Dort steht, der PoC
laufe „mit einem Wegwerf-Skript statt Produktcode". Der Inhaber hat sich
am 2026-09-07 dagegen entschieden: Der Exportschritt entsteht **unmittelbar
als Produktivcode** auf einem Feature-Branch, und die Abnahmekriterien
AK1–AK18 sowie die Negativtests N1–N19 des PoC-Plans laufen gegen diesen
Code statt gegen Wegwerfcode. Der Grund ist, dass Datenbaum,
Verschlüsselung und statischer Datenmodus in beiden Fassungen dieselben
wären und zweimal entstünden.

Was diese Abweichung **nicht** ändert: Der PoC-Teil, der einen Anbieter
braucht — Phase 2 des Plans, die Nachweise zur Reichweite des Tokens, zur
Zugriffsregel über den ganzen Hostnamen und zu den älteren
Deployment-Adressen —, bleibt unverändert Voraussetzung für die Annahme
dieses ADR. Er läuft mit synthetischen Daten, einem schreibbeschränkten
Token und vollständigem Rückbau. Bis dahin gibt es kein Anbieterkonto,
kein Token und keinen Upload; der Exporter schreibt in ein Verzeichnis.

Der Satz „und ein Prototyp im PoC, der nicht gemergt wird" unter
„Negativ und offen" ist damit gegenstandslos.

---

## Nachtrag vom 2026-09-08 — was die Umsetzung anders macht, und warum

Die Umsetzung liegt auf `feature/dashboard-export-extern`. Sie folgt den elf
Entscheidungen mit **zwei Abweichungen in Punkt 6**, beide aus demselben
Grund und beide bewusst. Sie stehen hier, damit in einem halben Jahr nicht
zu raten ist, ob es Absicht war.

**Erstens: In den Zusatzdaten der Verschlüsselung steht die Kennung des
Datenbaums, nicht die des einzelnen Exports.** Punkt 6 verlangte die
Export-Kennung. Sie hätte erzwungen, bei jedem Lauf **jede** Datei neu zu
verschlüsseln — auch die zweihundert Charts, an denen sich nichts geändert
hat — und damit jeden Lauf zu einem vollständigen Upload gemacht. Was die
Export-Kennung leisten sollte, nämlich das Einspielen einer Datei aus einem
anderen Stand, leistet stattdessen das **Manifest**: Es trägt je Pfad den
SHA-256 des Klartexts, wird bei jedem Export neu geschrieben und im Browser
geprüft. Das ist für die einzelne Datei mindestens gleichwertig — eine Datei,
die zu diesem Baum, aber nicht zu diesem Export gehört, fällt durch, auch
wenn sie sich einwandfrei entschlüsselt.

**Zweitens: Salt und Baumkennung sind stabil über viele Exporte**, nicht neu
je Export. Derselbe Grund: Ein neues Salt je Lauf ergäbe einen neuen
Schlüssel, damit neue Dateinamen und damit einen vollständig neuen Baum.
Gewechselt wird beides, wenn der Baum bewusst neu aufgesetzt wird. Ein
Wechsel der Passphrase allein wechselt sie **nicht** — er wechselt den
Schlüssel, und die alten Dateien verschwinden als verwaist.

### Drei Restrisiken, die dabei schärfer zu benennen sind

- **Der Änderungsverlauf je Datei liegt beim Anbieter offen.** Weil
  unveränderte Dateien nicht neu geschrieben werden und die opaken Namen
  stabil sind, sieht der Anbieter, welcher Name an welchem Tag neue Bytes
  bekam. Über die Zeit lassen sich Namen zu Aktien-Gruppen bündeln und deren
  Aktivität gegen öffentliche Marktereignisse halten. Das ist der Preis
  dafür, nicht bei jedem Lauf alles hochzuladen — dieselbe Sorte Profil, vor
  der die Auffüllung auf Größenklassen schützt, nur über die Zeitachse statt
  über die Größe. Wer das nicht will, zahlt es mit einem Vollupload je Lauf.
  Ebenso sichtbar: die **Zahl** der Dateien, und damit grob die Zahl der
  Läufe, Berichte, Messungen und Watchlist-Titel.
- **Das Zurückspielen eines vollständigen alten Standes bleibt offen und ist
  unbefristet möglich.** Manifest und Dateien zusammen sind in sich stimmig,
  jede Prüfsumme passt, die Verschlüsselung merkt nichts. Die Oberfläche
  führt deshalb den zuletzt gesehenen Exportzeitpunkt im Browser mit und
  warnt bei einem Rückschritt. Das ist ein Hinweis und kein Beweis: Der
  Vermerk gilt je Browser, ein anderes Gerät fängt bei null an, und wer ihn
  löscht, sieht die Warnung nicht mehr. Ein echter Anker wäre einer, den der
  Anbieter nicht schreiben kann — den gibt es hier nicht.
- **Stufe 1 komprimiert nicht.** Der Spike-Bericht (8.2) nennt Kompression
  „wo der Anbieter sie nicht selbst komprimiert"; die Umsetzung überlässt sie
  in Stufe 1 der Übertragungskompression des Anbieters und komprimiert erst
  in Stufe 2, wo sie zwingend ist. Da Stufe 2 unmittelbar folgt (E1), ist das
  ein Zwischenstand und keine Festlegung.

### Was zusätzlich entstanden ist, ohne im ADR zu stehen

- Eine **Sperre** gegen zwei gleichzeitige Exporte in dasselbe Verzeichnis.
  Ohne sie schreiben Tageslauf und Handbefehl zwei verschiedene Manifeste,
  und der Browser meldet danach Prüfsummenfehler — ein Fehlalarm, der genau
  wie der Angriff aussieht, gegen den die Prüfsumme steht.
- Ein Argument `--dashboard-export` an `cli dispatch`, wie Punkt 2 es
  verlangt: Geschaltet wird über die Aufgabenplanung, nicht über eine im
  öffentlichen Repository versionierte Datei. Damit ist auch der
  Notausschalter K3 des Spike-Berichts wörtlich ausführbar.
- Ein **Wächter** gegen eine Zustandsdatei innerhalb des veröffentlichten
  Verzeichnisses. Sie trägt die Zuordnung von Pfad zu opakem Namen; läge sie
  drinnen, wäre die Verschlüsselung der Dateinamen umsonst.

Der Status dieses ADR bleibt **Vorgeschlagen**. Punkt 10 bindet die Annahme
an den Proof of Concept beim Anbieter, und der steht aus.

---

## Nachtrag vom 2026-09-17 — angenommen, der PoC ist durch

Der Proof of Concept aus Abschnitt 11 des Spike-Berichts ist beim Anbieter
durchgeführt und abgenommen (Doc 14, **Stufe L**). Damit ist dieses ADR
**angenommen**, und was oben unter „Was dieses ADR ablöst" steht, gilt ab
jetzt.

**Gewählt wurde Cloudflare Workers mit Cloudflare Access**
([Anbieterevaluation](../requirements/f12-hosting-anbieter-evaluation.md)),
nicht Cloudflare Pages: Die Konsole legt inzwischen Worker mit statischen
Dateien an, und für diesen Zweck ist das der bessere Ort — eine einzige
Einstellung schützt jede Adresse des Workers einschließlich der Vorschauen,
und Vorschau-Adressen lassen sich ganz abschalten.

**Belegt ist damit die Kernbehauptung dieses ADR:** Echte Analysedaten
stehen außerhalb des Servers zur Verfügung, ohne dass der Server eine
eingehende Freigabe bekommen hat — und unterwegs war nichts davon lesbar.
Von 686 Dateien unter `data/` ist genau eine lesbarer Text: der
Klartextkopf. Die Anmeldung hat in fünf Proben niemanden ohne GitHub
durchgelassen, und der Schlüssel entsteht erst im Browser.

**AK16 ist erfüllt und deutlich übertroffen:** Vom Eingeben der Passphrase
bis zum sichtbaren Stand vergeht auf dem Smartphone **unter einer Sekunde**
gegen ein Ziel von zwei.

**Die beiden Entscheidungen, die noch offen waren, sind es nicht mehr.**
**O1** (Lizenzlage) ist am 2026-09-09 beschieden: Ein Anbieter, der
ausschließlich Chiffrat sieht, ist kein Empfänger der Daten. Die Lesart
trägt **Stufe 2 und nur diese** — aus der Reihenfolgeentscheidung E1 wird
damit eine Bedingung: `dashboard_export.encrypt` darf nicht `false` werden,
solange Finnhub-Abgeleitetes im Baum steht. **O3** ist am 2026-09-10
beschieden: GitHub als Identitätsanbieter.

**Was die Umsetzung noch schuldig bleibt** — Umsetzung, nicht Entscheidung:

1. ~~**Sicherheits-Header**~~ — **erledigt am 2026-09-17.**
   `frontend/public/_headers` liegt im Repository und kommt über
   `next build` in den Export. Die Messung hat ergeben: `'unsafe-inline'`
   ist bei `script-src` nicht zu vermeiden (Next legt je Seite sieben
   Inline-Skripte ab, die sich mit jedem Build ändern) und bei `style-src`
   ebenfalls nötig (`recharts` setzt zur Laufzeit `style`-Attribute).
   Zugelassen wurde es als bewusstes Zugeständnis, weil die beiden Senken,
   die es öffnet, heute verschlossen sind: Das Frontend setzt nirgends rohes
   HTML ein, und jedes `href`/`src` hat ein konstantes Präfix — sonst ließe
   `'unsafe-inline'` eine `javascript:`-URL aus Berichtsdaten zu. Zwei Tests
   bewachen genau diese beiden Annahmen.
   Alles Übrige ist streng: `default-src 'none'`, kein `eval`, keine fremde
   Herkunft, `frame-ancestors 'none'`, `no-store` für den Datenbaum.
2. ~~**Der Upload aus dem Exportschritt heraus**~~ — **erledigt am
   2026-09-18.** Siehe den Nachtrag unten.

**Ein Restrisiko hat sich durch die Anbieterwahl verschärft und steht hier
ausdrücklich:** Alte Worker-Versionen lassen sich bei Cloudflare **nicht
löschen**. Wegen des stabilen Salts (Nachtrag vom 2026-09-08) stehen alle je
hochgeladenen Fassungen unter demselben Schlüssel. Unerreichbar sind sie nur,
solange die Vorschau-Adressen abgeschaltet bleiben — was die
Konfigurationsdatei mit `"preview_urls": false` erzwingt, weil der
Vorgabewert dem eingeschalteten `workers_dev` folgt. Wer eine verratene
Passphrase wirklich loswerden will, löscht den ganzen Worker.

---

## Nachtrag vom 2026-09-18 — E4 umgesetzt, die Kette schließt sich

**Der Server sendet jetzt selbst.** Damit ist Punkt 2 der Schuldenliste
erledigt und die Entscheidung **E4** auf den Datenweg **DW2** festgelegt:
`wrangler` als Unterprozess, genau so, wie Doc 14, Stufe L es von Hand
erprobt hat. DW1 — ein Upload aus Python heraus — bleibt der schmalere Weg
und wird hier nicht gegangen: Cloudflares Schnittstelle für statische
Dateien ist mehrstufig (Version anlegen, Hash-Manifest melden, fehlende
Dateien senden, bereitstellen), und sie ohne das Werkzeug nachzubauen hieße,
ein Stück Anbieter-Protokoll zu pflegen, das der Anbieter selbst pflegt.

**Damit tritt Node in die produktive Kette.** Das zieht den in ADR 0052
vorgesehenen Nachtrag zu dessen Punkt 2 nach sich: Node ist nicht mehr nur
Bauwerkzeug, sondern läuft im nächtlichen Tageslauf mit. Die Fassung ist über
die Lock-Datei festgelegt — `wrangler` liegt als Entwicklungsabhängigkeit im
Frontend, `npm ci` installiert genau die geprüfte Fassung, die CI installiert
sie bei jedem Lauf und der Audit-Job sieht sie wöchentlich an. (`package.json`
nennt eine Caret-Spanne; wer `npm install` statt `npm ci` benutzt, hebt die
Nebenversion an und schreibt die Lock-Datei fort — das ist der bewusste
Unterschied zwischen Aktualisieren und Ausliefern.) Ein `npx wrangler@4`, wie
es von Hand erprobt wurde, hätte stattdessen bei jedem Nachladen eine
ungeprüfte Fassung in den Lauf geholt und ihn ans Netz gehängt.

**Ein fehlendes Werkzeug kostet den Upload, nicht den Lauf.** Die Suche nach
`wrangler` sitzt deshalb im Upload und nicht im Bau des Exportschritts: Der
läuft im Tageslauf vor dem Backfill, und ein Abbruch dort hätte Screening,
Analyse und Ergebnismeldung mitgenommen — die Umkehrung der Zusage aus
Punkt 2. Getroffen hätte es ausgerechnet den Handgriff, den die Betriebsdoku
selbst „leicht zu vergessen" nennt: das `npm ci` nach einem `git pull`.

**Ein drittes Ziel statt eines zweiten Schalters.** `dashboard_export.target`
kennt jetzt `none | directory | cloudflare`. Geschaltet wird wie bei den
Anbietern über ein Argument der Aufgabenplanung. Die mittlere Stufe ist
dabei mehr als ein Zwischenschritt: Sie ist die Rückfallebene, die den Baum
weiter schreibt, wenn der Weg nach draußen klemmt — besser als ein Export,
der ganz ausbleibt.

**Drei Ausgänge, drei Meldungen.** Der Kanal trägt weiterhin keine Inhalte
und keinen Link ([ADR 0040](0040-inhalt-der-ergebnismeldung.md)) und
zusätzlich nicht die Adresse des Dashboards (E6) — wohl aber die
Unterscheidung, die für das Handeln zählt: *nicht geschrieben* (Server und
Anbieter stehen gleich), *geschrieben, nicht gesendet* (der Server ist
voraus), *gesendet, aber Vorschau-Adressen aktiv*. Der dritte ist kein
Transportfehler, sondern ein Sicherheitsbefund. Keiner der drei lässt den
Lauf scheitern; das Ergebnis steht zu diesem Zeitpunkt in der Datenbank.

**Die Prüfung der Vorschau-Adressen sitzt jetzt im Schritt**, wie Doc 14,
Stufe L, Schritt 7 es verlangt — und sie besteht aus zwei ungleichen
Hälften. Die tragende ist, dass der Exportschritt die Konfigurationsdatei
**selbst schreibt**, vor jedem Upload: `"preview_urls": false` ist damit
eine Konstante im Code und keine Datei, die von Hand stimmen muss. Die
zweite liest die Ausgabe des Werkzeugs und meldet jede `*.workers.dev`-
Adresse, deren erstes Namensglied nicht der Worker-Name ist. Sie hängt
damit an der **Form der Adresse** und nicht am Wortlaut des Werkzeugs, und
sie ist ausdrücklich nur die Kanarienvogel-Schicht über der ersten.

**Drei Dinge hat erst die Review gefunden**, und alle drei hätten erst im
Betrieb wehgetan:

- **Der Starter in `bin/wrangler.js` ist nicht `wrangler`**, sondern ein
  Vorspann, der es als **eigenen Prozess weiterstartet** — mit geerbten
  Leitungen. Eine Zeitgrenze wäre daran vorbeigelaufen: Abgeschossen worden
  wäre der Vorspann, weitergeladen hätte der Enkel, und das Einsammeln der
  Ausgabe hätte unter Windows **ohne Zeitgrenze** auf Leitungen gewartet, die
  niemand mehr schließt — still, im nächtlichen Lauf, innerhalb der
  Exportsperre. Gestartet wird deshalb der Paket-Einstieg aus `main`.
- **Und die Ausgabe geht in Dateien statt in Leitungen.** Das ist der
  Nachschlag zum vorigen Punkt, und er kam erst vom **Windows-Lauf der CI**:
  Ein erster Anlauf ließ die Leitungen stehen und gab dem Einsammeln nach dem
  Abschuss nur eine Nachfrist — gemessen dauerte der Aufruf trotzdem
  30 Sekunden statt einer, weil unter Windows schon das *Schließen* einer
  Leitung auf den Lesefaden wartet, der am offenen Schreibende des Enkels
  hängt. Mit Dateien gibt es weder Lesefäden noch etwas zu schließen, und was
  bis zum Abschuss geschrieben wurde, bleibt lesbar. Gemessen danach:
  1,0 Sekunden. **Ohne den Windows-Job der CI wäre das erst auf dem Server
  aufgefallen** — und dort als stehender Nachtlauf, nicht als roter Test.
- **Die Ausgabe wird ausdrücklich als UTF-8 gelesen.** Ohne Angabe nimmt
  Python die Codierung des Systems, auf einem deutschen Windows `cp1252` —
  und daran zerbricht schon das erste Emoji, das das Werkzeug ausgibt. Der
  Upload wäre gelungen und der Schritt trotzdem gescheitert, gemeldet als
  „nicht aktualisiert", also als die Lage, die am wenigsten stimmt.
- **Eine `.env` neben der Konfigurationsdatei würde eingelesen.** Das Werkzeug
  tut das von sich aus; läge das Arbeitsverzeichnis in der Projektwurzel,
  bekäme es damit jedes `ATA_`-Geheimnis in die Hand — an der Erlaubnisliste
  vorbei, die genau das verhindern soll. Der Schritt bricht jetzt ab, wenn er
  dort eine findet.

**Zwei Zusagen, die vorher niemand gegeben hatte**, weil es keinen
Unterprozess gab:

1. **Das fremde Werkzeug sieht keine `ATA_`-Variable.** Der Unterprozess
   bekommt nicht die eigene Umgebung, sondern eine Erlaubnisliste. Die
   Passphrase des Datenbaums — das einzige Schloss vor den Daten — geht
   damit nie an einen Prozess, der mit dem Anbieter spricht. `NODE_OPTIONS`
   steht ebenfalls nicht darauf.
2. **Ohne Oberfläche geht nichts hinaus.** Fehlen `index.html` oder
   `_headers` im Verzeichnis, bricht der Schritt ab, bevor das Werkzeug
   startet. Sonst läge draußen Chiffrat ohne etwas, das es anzeigt — oder
   eine Seite ohne ihre Sicherheits-Header, und das fiele niemandem auf.

**Was bewusst nicht gebaut wurde: „nur hochladen, wenn sich etwas geändert
hat".** Das Manifest trägt den Exportzeitpunkt und ändert sich in jedem
Lauf; die Regel träfe nie zu und wäre toter Code. Eine Regel, die das
Manifest ausnähme, ließe draußen einen alten „Stand" stehen — das wäre
schlechter als eine Worker-Version mehr. Das verschärfte Restrisiko oben
bleibt davon unberührt: Jeder Lauf erzeugt eine Fassung, und keine davon
lässt sich löschen.

**Ebenfalls nicht gebaut: der nächtliche Bau der Oberfläche.** `npm run
build` im Zero-Knowledge-Modus bleibt Handarbeit aus Doc 14, Stufe K,
Schritt 2. Wer das Frontend ändert und diesen Schritt vergisst, schickt eine
alte Oberfläche mit neuen Daten hinaus — der Upload prüft nur, dass
überhaupt eine da ist, nicht welche.

## Nachtrag vom 2026-09-19 — Bau der Oberflaeche und E5

Der Bau der Oberflaeche ist keine Handarbeit mehr: `cli publish --full` baut
sie im Zero-Knowledge-Modus und legt sie in das veroeffentlichte Verzeichnis,
bevor der Baum geschrieben wird. Der Tageslauf baut weiterhin nicht. Und
E5 ist umgesetzt: Die Ergebnismeldung traegt den Link zum Lauf im Dashboard,
nur mit Export zum Anbieter und nur verschluesselt. Beides in
[ADR 0065](0065-oberflaechen-build-im-exportschritt-und-dashboard-link.md).
