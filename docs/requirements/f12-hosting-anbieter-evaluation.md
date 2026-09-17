# Anbieter für das Dashboard außerhalb des Servers

Stand 2026-09-09. **Vorschlag, nicht entschieden** — die Wahl trifft der
Inhaber, und sie ist Voraussetzung für die Annahme von
[ADR 0060](../adr/0060-dashboard-ausserhalb-des-servers.md).

Der [Spike-Bericht](f12-externes-hosting-spike.md) nennt Cloudflare Pages
und Azure Static Web Apps ausdrücklich nur **beispielhaft** und lässt die
Wahl offen (Abschnitt „Kennzeichnung in diesem Dokument"). Dieses Dokument
holt die Bewertung nach.

## Was gesucht wird

Die Umsetzung steht: Der Server schreibt einen verschlüsselten Datenbaum
(Stufe 2, Zero-Knowledge). Gesucht ist ein Ort, der ihn ausliefert. Damit
sind die üblichen Hosting-Fragen — Baupipeline, Serverless-Funktionen,
Frameworks — **ohne Belang**. Es geht um statische Dateien und darum, wer
sie sehen darf.

Die Anforderungen stammen aus Abschnitt 8.3 des Spike-Berichts, ergänzt um
das, was die Serverabnahme am 2026-09-09 gemessen hat:

| # | Anforderung | Herkunft |
|---|---|---|
| A | Zugriffsregel deckt den **ganzen Hostnamen** ab — auch `data/*`, auch Vorschau- und ältere Deployment-Adressen, auch die Standard-Subdomain neben einem eigenen Namen | N1–N4, T3 |
| B | Die Regel liegt **außerhalb des Deployments** — liegt sie in einer Datei darin, hebt ein Token-Dieb sie mit dem nächsten Upload auf | N19 |
| C | **Alte Deployments löschbar** — sonst ist die Historie eine Halde aller Snapshots | T20, O2 |
| D | Anmeldung über **Identitätsanbieter mit Authenticator-App oder Passkey**, genau ein erlaubter Nutzer | E2, P1 |
| E | **Deploy-Recht je Projekt**, nicht je Konto | AK9 |
| F | Kostenlose Stufe trägt **30 MB je Deployment, täglich** | Messung 2026-09-09 |
| G | Eigene **Sicherheits-Header** setzbar (CSP, `nosniff`, `Referrer-Policy`, `frame-ancestors`, `Cache-Control: no-store` für `data/*`) | 8.3 |

**Anforderung C wiegt hier schwerer als anderswo**, und das hat einen
Grund, der erst mit der Umsetzung entstanden ist: Der Datenbaum benutzt ein
**stabiles Salt** und eine gleichbleibende Baumkennung, damit der Upload
inkrementell sein kann. Alle je hochgeladenen Fassungen sind deshalb unter
**demselben Schlüssel** verschlüsselt. Wer die Passphrase eines Tages
erlangt, liest damit nicht einen Stand, sondern jeden aufbewahrten. Eine
unbegrenzte Deployment-Historie ist unter dieser Konstruktion kein
Schönheitsfehler, sondern ein wachsendes Archiv.

## Die Bewerber

| Anbieter | A ganzer Host | B Regel außerhalb | C löschbar | D MFA | E Token je Projekt | F 30 MB/Tag | G Header |
|---|---|---|---|---|---|---|---|
| **Cloudflare Pages + Access** | ✔ (mit Vorbehalt, s. u.) | ✔ | ✔ (`wrangler`) | ✔ | ✖ kontoweit | ✔ | ✔ `_headers` |
| Azure Static Web Apps | ✔ | **✖ im Deployment** | ✔ | ✔ Entra ID | ✔ Deployment-Token je App | ✔ | ✔ Konfigdatei |
| Netlify | ✔ | ✔ | ✔ | (✔) | ✔ | ✔ | ✔ |
| Vercel | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| GitHub Pages | **✖** | — | ✖ | — | ✔ | ✔ | ✖ |
| **AWS S3 + CloudFront** | ✔ | ✔✔ | ✔✔ (s. u.) | **✖ nur mit eigenem Code** | ✔✔ IAM je Bucket | ✔ | ✔✔ |

### Was die Zeilen bedeuten

**Azure Static Web Apps scheidet an Anforderung B aus.** Die Zugriffsregeln
stehen in `staticwebapp.config.json`, und diese Datei liegt **im
Deployment**. Wer das Deploy-Token hat, ändert mit dem nächsten Upload die
Regel, die ihn aufhalten soll. Das ist genau die Bedrohung N19, und sie
trifft hier nicht als Nachlässigkeit, sondern als Produktentwurf. Dass die
freie Stufe zusätzlich nur die eingebauten Identitätsanbieter erlaubt
(eigene Anbieter erst im Standard-Tarif), fällt daneben kaum ins Gewicht.

**Netlify und Vercel scheitern am Preis der Anmeldung.** Bei Netlify sind
Passwortschutz und Basic Auth für Konten, die nach dem 2025-09-04 angelegt
wurden, Pro-Merkmale; die freie Stufe kennt nur Sichtbarkeitseinstellungen.
Bei Vercel kostet Password Protection 20 $ je Monat und Projekt und ist auf
Hobby gar nicht verfügbar. Vercel Authentication ist zwar auch auf Hobby
kostenlos und schützt alle Deployment-Adressen — aber sie bindet die
Anmeldung an ein Vercel-Konto, und der Hobby-Tarif ist auf nicht-gewerbliche
Nutzung beschränkt. Beides ist nicht disqualifizierend, aber es ist teurer
oder enger als die Alternative, ohne etwas zu gewinnen.

**GitHub Pages scheidet an Anforderung A aus.** Es gibt dort keine
Zugriffskontrolle vor der Seite; „private Pages" sind ein
Enterprise-Merkmal. Der Baum stünde offen im Netz. Das *wäre* mit Stufe 2
technisch verkraftbar — draußen liegt nur Chiffrat —, hieße aber, auf die
Anmeldung an der Kante ganz zu verzichten. Die Entscheidungsmatrix des
Spikes bewertet genau das (H3 allein gegen H3+H1) und kommt bei
Authentifizierung auf `−` statt `++`. Für einen Baum, dessen einziges
Schloss dann eine Passphrase ist, ist das die falsche Richtung.

### AWS S3 mit CloudFront — nachgetragen am 2026-09-09

Auf Nachfrage des Inhabers bewertet, der dort ein Konto hat und die
Plattform kennt. **S3 allein scheidet aus:** Der Website-Endpunkt eines
Buckets spricht nur HTTP, und S3 (TLS für alle externen Verbindungen)
verlangt HTTPS. Bewertet wird deshalb S3 **mit CloudFront** davor.

**Bei drei Kriterien ist das die beste Antwort im ganzen Feld:**

- **E (Deploy-Recht je Projekt):** Eine IAM-Richtlinie lässt sich auf genau
  einen Bucket-ARN und auf `PutObject`, `DeleteObject`, `ListBucket`
  einengen. Das ist das Kriterium, an dem Cloudflare scheitert und dort ein
  eigenes Konto als Umweg braucht. Hier braucht es keinen Umweg.
- **B (Regel außerhalb des Deployments):** Bucket-Richtlinie und
  CloudFront-Verteilung liegen nicht in den Objekten. Wer nur schreiben
  darf, kann die Regel davor nicht anfassen — und anders als bei einem
  Anbieter-Schalter ist das nachweisbar, weil es in der IAM-Richtlinie
  steht.
- **G (Sicherheits-Header):** Eine Response-Headers-Policy in CloudFront,
  ebenfalls außerhalb des Deployments.

**Bei C ist es sogar strukturell besser — mit einer Falle.** Es gibt gar
keine Deployment-Historie: Der Upload überschreibt Objekte, alte Fassungen
verschwinden von selbst. Genau deshalb ist **Bucket-Versionierung hier
gefährlich**. Ist sie eingeschaltet — und sie ist es oft, aus guten
Gründen —, bewahrt der Bucket jede je hochgeladene Fassung auf, und wegen
des stabilen Salts stehen alle unter demselben Schlüssel. Aus dem Vorteil
wird dann der schlimmste Fall des Feldes. Versionierung muss aus sein, oder
eine Lebenszyklusregel muss ältere Fassungen verfallen lassen.

**Die Lücke ist D, und sie ist nicht klein.** AWS hat für CloudFront **keine
verwaltete Anmeldung**. Jeder dokumentierte Weg — Cognito, Okta, Auth0 —
läuft über **Lambda@Edge**: eine Funktion, die Cookies prüft, JWTs
validiert und den OIDC-Fluss abwickelt. Das ist Sitzungscode, den der
Inhaber besitzt, betreibt und patcht. Abschnitt 8.3 schließt genau das aus
(„kein eigenes Anmeldeformular, kein eigener Sitzungscode"), und
Kriterium 10 der Entscheidungsmatrix bewertet Patch- und Betriebsaufwand.
Für ein System, dessen erklärter Vorzug ist, dass draußen nichts zu
patchen ist, wäre eine selbstbetriebene Authentifizierungsfunktion der
teuerste einzelne Rückschritt.

**Zwei verwaltete Auswege, beide mit Preis:**

1. **AWS Amplify Hosting** vor dem Bucket: Der Zugriffsschutz ist ein
   Schalter in der Konsole — Benutzername und Passwort, kein Code. Damit
   ist D formal verletzt (ein geteiltes Passwort statt Anmeldung über einen
   Identitätsanbieter mit Authenticator-App), aber es ist eine echte,
   verwaltete Schranke.
2. **CloudFront Functions mit Basic Auth**: rund zehn Zeilen, zustandslos,
   kein Cookie, kein Tokentausch. Weniger als Lambda@Edge, aber immer noch
   eigener Code an der Kante.

**Einordnung.** Gemessen an den Kriterien, wie sie geschrieben sind, bleibt
Cloudflare vorn: Sein einziger Fehler (E) hat einen sauberen Ausweg — ein
eigenes Konto —, während der Fehler von AWS (D) nur durch eigenen Code oder
durch eine Änderung der Entscheidung **E2** zu beheben ist.

Die Änderung von E2 ist allerdings **vertretbar und nicht abwegig**, und
zwar aus einem Grund, der zum Zeitpunkt von E2 noch nicht galt: Damals war
Stufe 1 im Spiel, und die Kantenanmeldung war das **einzige** Schloss vor
Klartext. Seit der Entscheidung zu O1 gibt es Stufe 1 nicht mehr. Draußen
liegt nur Chiffrat, und das eigentliche Schloss ist die Passphrase. Die
Kantenanmeldung hält dann Scanner und Neugierige ab und verbirgt, dass es
die Seite gibt — dafür genügt ein geteiltes Passwort über TLS.

Dagegen steht etwas, das keine Tabelle abbildet: **Wer den Notausschalter
in der Hand hat, muss ihn im Ernstfall finden.** Abschnitt 12 verlangt
Rückbau und Abschaltung unter Zeitdruck. Eine Konsole, die der Inhaber
kennt, ist dabei mehr wert als eine Zeile in einer Bewertungstabelle.

**Damit ist es eine Entscheidung des Inhabers und keine Rechnung**, und sie
lautet nicht „AWS oder Cloudflare", sondern: **Soll die Anmeldung an der
Kante MFA über einen Identitätsanbieter sein (dann Cloudflare), oder genügt
ein zweites, geteiltes Passwort vor dem Chiffrat (dann AWS)?**

### Nachgefragt: S3-Website-Hosting mit Passwort auf der Seite selbst

Vorschlag des Inhabers: den Bucket als Website ausliefern und die Anmeldung
auf der Seite erledigen — „so wie es gerade auf dem Windows-Server läuft".

**Erstens: Das ist, richtig gemacht, bereits gebaut.** Die Passphrase-Abfrage
in `Datenzugang.tsx` *ist* ein Passwort auf der Seite selbst. Der Vorschlag
ist damit kein dritter Weg, sondern die Frage, ob die Anmeldung an der
Kante zusätzlich nötig ist.

**Zweitens: Es ist etwas anderes als die Anmeldung auf dem Server, und der
Unterschied ist der ganze Punkt.** Auf dem Windows-Server prüft FastAPI das
Passwort, setzt ein signiertes Sitzungs-Cookie und **hält die Daten
zurück**, solange es fehlt. Ein Bucket hält nichts zurück: Er liefert
Objekte an jeden aus, der die Adresse kennt. Eine Anmeldemaske im Browser
könnte niemandem etwas verweigern — sie liefe im selben JavaScript, das der
Besucher kontrolliert.

Daraus folgt eine Regel, die keine Ausnahme verträgt: **Die
Sitzungsanmeldung des Servers darf im statischen Build nicht nachgebaut
werden.** Sie sähe aus wie Schutz, wäre keiner, und sie verführte dazu,
dahinter Klartext abzulegen. Was auf statischem Hosting schützt, ist
ausschließlich die Verschlüsselung — nicht eine Entscheidung, die niemand
trifft. Deshalb steht in 8.3 „kein eigenes Anmeldeformular, kein eigener
Sitzungscode", und deshalb bleibt `ATA_SESSION_SECRET` reserviert.

**Drittens, und das entscheidet die Frage: Der Website-Endpunkt eines
Buckets spricht nur HTTP.** Ohne TLS liefert er auch **das JavaScript**
unauthentifiziert aus — und dieses JavaScript nimmt die Passphrase
entgegen und leitet den Schlüssel ab. Wer auf dem Weg sitzt (fremdes WLAN,
Hotelnetz, Mobilfunk-Zwischenstelle), tauscht es aus und bekommt die
Passphrase geschenkt. Damit ist nicht ein Stand kompromittiert, sondern
**jeder je exportierte**, denn alle stehen unter demselben Schlüssel.

Zero-Knowledge trägt nur, solange die **Auslieferung des Codes**
authentifiziert ist. Das ist keine Härtung, das ist die Voraussetzung. Der
REST-Endpunkt des Buckets kann zwar HTTPS, kennt aber keine
Index-Dokumente — der statische Export mit `trailingSlash: true` verlangt,
dass `/aktie/` zu `/aktie/index.html` wird. Es läuft also auf CloudFront
hinaus, und „S3 Static Website Hosting" als eigenständige Antwort löst sich
damit auf.

**Was bleibt, wenn man auf die Kantenanmeldung verzichtet** (S3 + CloudFront,
nur Passphrase):

- Das Chiffrat ist **öffentlich abrufbar**. Ein Angreifer lädt alle 685
  Dateien und rechnet **offline** gegen die Passphrase, mit eigener
  Hardware und ohne Zeitdruck. 600.000 Runden PBKDF2 verteuern das, aber
  die Passphrase ist dann die **einzige** Verteidigung. Sie hält — weil sie
  32 zufällige Bytes aus dem Passwortmanager ist (O8). Wäre sie ausgedacht,
  wäre dieser Weg fahrlässig.
- Dateizahl, Größenklassen und **Änderungszeitpunkte** sieht nicht mehr nur
  der Anbieter, sondern jeder (R1).
- Kein Anmeldeprotokoll, keine Ratenbegrenzung, kein „überall abmelden"
  (K5, Kriterium 9).
- Dass es die Seite gibt, ist öffentlich. Nichtssagender Name, `robots.txt`
  und `noindex` (T9) sind dann die einzige Deckung.

Das ist genau die Spalte **H3 allein** der Entscheidungsmatrix: `−` bei der
Authentifizierung, `+` statt `++` beim Schutz vor Datenabfluss durch
Fehlkonfiguration.

## Empfehlung: Cloudflare Pages mit Cloudflare Access

**Warum.** Es ist der einzige Bewerber, der Anforderung B sauber erfüllt:
Die Zugriffsregel ist eine **Access-Anwendung in der Zero-Trust-Konsole**,
vollständig getrennt vom Deployment. Ein gestohlenes Deploy-Token kann den
Inhalt ersetzen — es kann die Regel davor nicht anfassen. Dazu kommt: Die
freie Stufe von Zero Trust deckt bis zu 50 Nutzer, gebraucht wird genau
einer; die Anmeldung läuft über einen Identitätsanbieter mit
Authenticator-App oder Passkey (D); Header kommen aus einer `_headers`-Datei
(G); und alte Deployments lassen sich mit
`wrangler pages deployment delete` einzeln entfernen (C).

**Drei Dinge, die dabei schiefgehen können, und keines davon ist theoretisch:**

1. **Der Schalter „Enable access policy" in den Pages-Einstellungen schützt
   nur die Vorschau-Deployments** — nicht `*.pages.dev` und nicht die eigene
   Domain. Wer ihn setzt und sich in Sicherheit wiegt, hat den
   Produktivstand offen im Netz. Die Regel für den Produktivnamen muss als
   **eigene Access-Anwendung** angelegt werden, und zwar für **beide**
   Hostnamen. Das ist wörtlich Bedrohung N1–N4 aus dem Spike, und es ist der
   Grund, warum Anforderung A oben mit Vorbehalt steht.
2. **Vorschau-Adressen bleiben dauerhaft erreichbar**, bis das Deployment
   gelöscht wird. Zusammen mit dem stabilen Salt heißt das: Jede alte
   Fassung bleibt unter derselben Passphrase lesbar. Das Aufräumen gehört
   deshalb in den Upload-Schritt und nicht in einen guten Vorsatz — und der
   jüngste Stand eines Zweigs lässt sich nicht löschen, das Aufräumen muss
   also die Historie meinen und nicht den Kopf.
3. **Anforderung E erfüllt Cloudflare nicht.** Das Recht
   `Cloudflare Pages: Edit` gilt **kontoweit**; ein Token lässt sich nicht
   auf ein einzelnes Projekt einengen. Der Ausweg ist ein **eigenes
   Cloudflare-Konto ausschließlich für dieses Projekt**. Dann ist „kontoweit"
   und „projektweit" dasselbe, und der Verlust des Tokens kostet nichts
   außerhalb dieses Dashboards. Ein bestehendes Konto mit anderen Domains
   dafür zu benutzen, wäre der bequeme und der falsche Weg.

**Kosten:** 0 € bei einem Nutzer, einem Projekt und 30 MB je Deployment.

**Was der PoC noch prüfen muss**, bevor daraus eine Entscheidung wird: die
Sitzungseinstellungen der Anmeldung (AK6), ob die CSP den statischen Export
ohne `'unsafe-inline'` trägt, ob `wrangler` als Unterprozess auf dem
Windows-Server tragfähig ist (E4, DW2) oder ob die HTTP-Schnittstelle für
DW1 reicht, und die Nutzungsbedingungen der freien Stufe (O2).

## Quellen

Abgerufen am 2026-09-09.

- [Cloudflare Zero Trust: freie Stufe bis 50 Nutzer](https://zerometric.net/research/cloudflare-zero-trust-free-plan-limits-2026/)
- [Cloudflare Pages: Zugriffsregel schützt nur Vorschau-Deployments](https://jarrodnix.dev/blog/blocking-access-to-deployment-and-project-pages-dev-domains-in-cloudflare-pages/)
- [Cloudflare Pages: Vorschau-Adressen bleiben erreichbar](https://israynotarray.com/en/misc/2026/05/13/cloudflare-pages-preview-urls-stay-forever-lock-with-access/)
- [Cloudflare Pages: Deployments einzeln löschen](https://developers.cloudflare.com/pages/platform/known-issues/)
- [Cloudflare API-Token lassen sich nicht auf ein Pages-Projekt einengen](https://community.cloudflare.com/t/restrict-api-token-to-specific-cloudflare-pages-project/425645)
- [Azure Static Web Apps: Zugriffsregeln in `staticwebapp.config.json`](https://learn.microsoft.com/en-us/azure/static-web-apps/configuration)
- [Netlify: Passwortschutz ist Pro-Merkmal für neue Konten](https://netli.fyi/blog/restrict-access-netlify-site-with-passwords)
- [Vercel: Password Protection nur ab Pro](https://vercel.com/docs/deployment-protection/methods-to-protect-deployments/password-protection)
- [CloudFront-Anmeldung nur über Lambda@Edge (AWS-Beispiel mit Cognito)](https://github.com/aws-samples/cloudfront-authorization-at-edge)
- [AWS Amplify Hosting: Zugriffsschutz per Benutzername und Passwort](https://docs.aws.amazon.com/amplify/latest/userguide/deploy-website-from-s3.html)
- [Amplify Hosting kann direkt aus einem S3-Bucket ausliefern](https://aws.amazon.com/about-aws/whats-new/2024/10/aws-amplify-amazon-s3-static-website-hosting)
