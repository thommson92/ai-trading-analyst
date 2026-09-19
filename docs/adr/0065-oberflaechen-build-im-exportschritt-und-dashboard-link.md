# ADR 0065: Der Bau der Oberfläche im Exportschritt und der Link zum Dashboard in der Ergebnismeldung

- Status: Angenommen
- Datum: 2026-09-19

## Kontext

Zwei Punkte, die [ADR 0060](0060-dashboard-ausserhalb-des-servers.md)
bewusst offen ließ:

1. **Der Bau der Oberfläche war Handarbeit** (Doc 14, Stufe K, Schritt 2).
   Der Exportschritt prüfte nur, dass `index.html` und `_headers` im
   veröffentlichten Verzeichnis liegen — nicht, welche Oberfläche. Am
   2026-09-18 ist genau das passiert: Nach dem ersten Redesign-Schritt
   ging mit `publish` die alte Oberfläche zu neuen Daten hinaus, und der
   Inhaber sah keine Änderung. Mit sechs Frontend-Phasen im Redesign
   ([ADR 0063](0063-dashboard-redesign.md)) wiederholte sich das bei jedem
   Merge.
2. **Die Ergebnismeldung nennt kein Dashboard.** [ADR 0040](0040-inhalt-der-ergebnismeldung.md)
   verneinte den Link, ADR 0060 (E5) erlaubte ihn „erst nach Stufe 2, dann
   ja". Stufe 2 ist seit dem 2026-09-17 in Betrieb. Die Adresse lässt sich
   aus den vorhandenen Variablen nicht bauen: `ATA_DASHBOARD_PUBLISH_ACCOUNT`
   ist die Konto-Kennung, nicht die Subdomain von `workers.dev`.

Der Inhaber hat beides am 2026-09-18 für den Plan bestätigt.

## Entscheidung

1. **`cli publish --full` baut die Oberfläche selbst**, bevor es den
   Datenbaum schreibt: `next build` im Zero-Knowledge-Modus
   (`NEXT_PUBLIC_DATENMODUS=verschluesselt`), gestartet über den Einstieg
   des `next`-Pakets — derselbe Prozessstart wie beim Upload:
   Argumentliste, Erlaubnisliste für die Umgebung (kein `ATA_`-Geheimnis,
   kein `NODE_OPTIONS`), Ausgabe in Dateien, Zeitgrenze
   (`dashboard_export.build_timeout_seconds`, 600 s). Danach wird das
   veröffentlichte Verzeichnis geleert — **außer `data/`**, das dem
   Exportschritt gehört — und der Bau hineinkopiert. Scheitert der Bau,
   wird nichts geschrieben und nichts gesendet; Server und Anbieter bleiben
   beide auf dem alten Stand.
2. **Nur bei `--full`, und `--ohne-build` schaltet es ab.** Der Tageslauf
   baut nicht: Er schreibt nur Daten, und eine Oberfläche, die sich jede
   Nacht neu baut, wäre ein Bau ohne Änderung. Wer nur den Baum neu
   schreiben will, sagt `--full --ohne-build`.
3. **Der Zero-Knowledge-Build bekommt sein eigenes Verzeichnis**
   (`frontend/out-verschluesselt`, über `distDir` in `next.config.ts`).
   Der LAN-Build in `frontend/out` bleibt stehen; Doc 14 verliert damit
   den Schritt „LAN-Build sofort wiederherstellen". Das Zwischenverzeichnis
   `.next` teilen sich beide — nie parallel bauen; die Exportsperre deckt
   den Tageslauf, `publish` läuft von Hand.
4. **Die Ergebnismeldung trägt den Link zum Lauf** —
   `https://<worker>.<subdomain>.workers.dev/laeufe/?id=<lauf>` — aus der
   neuen Variablen `ATA_DASHBOARD_URL`. Sie wird beim Start geprüft:
   `https://`, genau die Form des Anbieters, und der erste Namensteil muss
   `ATA_DASHBOARD_PUBLISH_WORKER` entsprechen. Ohne Variable kein Link und
   kein Fehler; mit falscher Variable kein Start — ein falscher Link in
   jeder Meldung wäre schlimmer als keiner.
5. **Nur mit Export zum Anbieter und nur verschlüsselt** (E5). Der Link
   steht **vor** den Kandidatenblöcken, weil der Kanal am Ende kürzt; er
   nennt kein Symbol, weil die Adresse über ein fremdes Netz geht. Dazu der
   Hinweis, dass der Stand dort erst nach dem Export steht — die Meldung
   geht vor dem Export hinaus, und der dauert eine Viertelstunde.
6. **Was nicht gebaut wird:** ein Bau im Tageslauf, ein Link je Kandidat,
   `npm ci` aus dem Exportschritt (bleibt Handarbeit nach `git pull`).

## Konsequenzen

- Doc 14, Stufe K, Schritt 2 wird zu `cli publish --full`; die
  PowerShell-Zeilen zum Bauen und Kopieren entfallen. Die Abnahme auf dem
  Server: `publish --full --dashboard-export cloudflare` baut, kopiert,
  schreibt, sendet; `frontend/out` bleibt unverändert; die nächste Meldung
  trägt den Link.
- Nachträge: ADR 0060 (Bau nicht mehr Handarbeit; E5 umgesetzt), ADR 0040
  (der Link ist erlaubt, unter den Bedingungen von E5).
- Eine neue Variable in `.env` des Servers: `ATA_DASHBOARD_URL`.
