# ADR 0052: Das Dashboard wird als statischer Export von der API mit ausgeliefert

- Status: Angenommen
- Datum: 2026-09-01

## Kontext

Sprint 6 baut das Dashboard. [ADR 0049](0049-dashboard-mvp-nur-lan.md) hat es
auf das eigene Netz begrenzt — keine Exposition, keine eigene
Authentifizierung. Damit wird die Frage fällig, die
[ADR 0036](0036-nativer-windows-betrieb.md) ausdrücklich an diesen Sprint
vertagt hat: Wie kommt das Frontend auf den Server, und braucht es dafür
Container und Reverse Proxy?

Die Ausgangslage: Das Next.js-Gerüst stammt aus Sprint 0 und wird nicht
ausgeliefert (`docs/13 - Deployment.md`). Der Server betreibt heute **keinen
Dauerprozess** — der Dispatcher ist ein idempotenter Einzelstart
([ADR 0019](0019-trading-day-dispatcher.md)), ausgelöst von der
Aufgabenplanung. Ein Dashboard ist der erste Bestandteil, der dauerhaft
laufen muss.

Drei Wege standen zur Wahl: (a) ein statischer Export, ausgeliefert von der
ohnehin nötigen FastAPI-Anwendung; (b) zwei native Prozesse, `uvicorn` und
`next start`; (c) ein Container-Verbund mit Reverse Proxy.

## Entscheidung

**Weg (a).** Das Frontend wird mit `output: 'export'` zu statischen Dateien
gebaut; die FastAPI-Anwendung liefert diesen Ordner unter `/` mit aus. Ein
Prozess, ein Port, gleiche Herkunft — und damit kein CORS.

Festgeschrieben wird:

1. **Kein Container, kein Reverse Proxy.** Die von ADR 0036 vertagte Frage
   ist damit beantwortet, und zwar mit demselben Ergebnis wie damals. Der
   Anlass, der die Neubewertung auslösen sollte — „etwas, das ausgeliefert
   werden muss" —, ist eingetreten, verlangt aber keinen Container: Ein
   Ordner statischer Dateien wird von dem Prozess mitgeliefert, der für die
   API ohnehin läuft.
2. **Node ist Bauwerkzeug, nicht Laufzeit.** `npm ci && npm run build`
   gehört in den Aktualisierungsablauf auf dem Server (Doc 13/14); danach
   läuft dort kein Node-Prozess.
3. **`uvicorn` wird ein Autostart-Eintrag der Aufgabenplanung** („Bei
   Systemstart"), gebunden an die LAN-Schnittstelle, mit einer
   Firewall-Freigabe **nur im privaten Profil** und ohne Portweiterleitung
   am Router. Das ist die Präzisierung zu ADR 0049: „nur an lokale
   Schnittstellen" heißt erreichbar im eigenen Netz, nicht darüber hinaus.
4. **Fehlt der Exportordner, startet die API trotzdem.** Der Batchbetrieb
   darf nicht daran hängen, ob ein Frontend gebaut wurde.

## Begründung

**Der zweite Prozess kostet dauerhaft, und der Gegenwert entsteht hier
nicht.** `next start` verlangt Node als Laufzeit, einen zweiten
Autostart-Eintrag, einen zweiten Port und eine CORS-Regelung — für ein
Dashboard mit drei Ansichten, dessen Daten ausnahmslos aus einer API kommen.
Serverseitiges Rendern zahlt sich gegen Suchmaschinen, gegen Erstaufrufzeiten
bei vielen Besuchern und gegen schwache Endgeräte aus. Nichts davon liegt
vor: ein Leser, im eigenen Netz, an einem Rechner, der die TWS betreibt.

**Für Container gilt unverändert, was ADR 0036 begründet hat.** Die TWS ist
eine Desktop-Anwendung mit angemeldeter Windows-Sitzung
([ADR 0018](0018-kein-windows-autologon.md)) und zugleich die Quelle aller
Kursdaten; sie bliebe außerhalb jedes Verbunds. Ein Reverse Proxy erfüllt
seinen Zweck erst mit externem Zugriff und TLS — und genau der ist nach
ADR 0049 bewusst nicht Teil des MVP. Container jetzt einzuführen hieße, den
abgenommenen Betrieb gegen einen ungetesteten zu tauschen, um ein Problem zu
lösen, das erst mit der Exposition entsteht.

**Der Preis ist benannt, nicht versteckt.** Ein statischer Export kann nicht
alles, was Next.js kann — siehe Konsequenzen. Für ein Dashboard, das
gespeicherte Berichte anzeigt, ist keine dieser Fähigkeiten nötig.

## Konsequenzen

- **Kein SSR, keine Route Handler, keine Server Actions.** Das Frontend ist
  ein Browser-Client der API und sonst nichts. Das deckt sich mit der Regel
  „keine Geschäftslogik im Frontend" (Doc 12).
- **Dynamische Pfadsegmente sind nicht möglich.** Eine `[id]`-Route verlangt
  im Export `generateStaticParams`, also alle Werte zur Bauzeit; Berichts-IDs
  entstehen zur Laufzeit. Berichte werden deshalb über **Query-Parameter**
  adressiert (`/bericht/?id=…`). Wer das übersieht, merkt es erst am
  brechenden Build.
- **`trailingSlash: true`**, damit jede Route als Verzeichnis mit
  `index.html` entsteht — genau die Form, die ein statischer Dateiserver ohne
  Sonderregeln findet.
- **Node muss auf dem Server installiert sein**, sonst gibt es keinen Build.
  Ob es das ist, ist unbelegt und vor der Auslieferung zu prüfen.
- Die Aktualisierung wird um einen Schritt länger (`npm ci && npm run build`
  neben `pip install` und `alembic upgrade head`).
- **Diese Entscheidung ist eine Stufe, kein Endzustand** — wie ADR 0049.
  Kommt die externe Erreichbarkeit, kommen Reverse Proxy und TLS zurück auf
  den Tisch, und mit ihnen darf auch die Container-Frage erneut gestellt
  werden.
