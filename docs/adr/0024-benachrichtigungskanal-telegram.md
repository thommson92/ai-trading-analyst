# ADR 0024: Telegram als Benachrichtigungskanal (F10)

- Status: Angenommen
- Datum: 2026-08-22

## Kontext

[ADR 0019](0019-trading-day-dispatcher.md) hat den **Auslöser** für Meldungen
gebaut und den **Kanal** ausdrücklich offengelassen: „Der Kanal ist als F10
offen (`notifications.channel: dry_run`) und bekommt ein eigenes ADR, weil ein
Push-Dienst eine externe Abhängigkeit mit Zugangsdaten ist."

Seither steht alles bereit außer der Zustellung: der Port `Notifier`, die
Meldung bei abgelaufener Nachholfrist, die Einmal-Zustellung je Lauf über
`alert_sent`, und ein `build_notifier`, das einen nicht gebauten Kanal
abweist statt still nichts zu senden.

Die Dringlichkeit kommt aus dem Betrieb. Mit Stufe F der Inbetriebnahme
([Doc 14](../14%20-%20Inbetriebnahme%20und%20Betrieb.md)) läuft der Screener
unbeaufsichtigt über die Windows-Aufgabenplanung. Fällt ein Tageslauf aus —
TWS nicht angemeldet, Datenbank weg, Anbieter still —, bemerkt das heute
niemand, solange niemand ins Protokoll sieht. Ein übersprungener Handelstag
ist genau die Sorte Fehler, die nicht auffällt.

## Entscheidung

**Telegram Bot API als Kanal**, angesprochen über einen einzelnen
HTTP-POST auf `sendMessage`.

### 1. Warum Telegram

| Kriterium | Telegram | Pushover | ntfy.sh | SMTP |
|---|---|---|---|---|
| Kosten | keine | einmalig ~5 USD je Plattform | keine | keine |
| Zugangsdaten | Bot-Token (geheim) + Chat-ID (nicht geheim) | zwei geheime Werte | Topic-Name | Server, Port, TLS, Konto |
| Zustellung aufs Telefon | Push der Telegram-App | reiner Alarmdienst | Push der ntfy-App | hängt an der Mail-App |
| Konfigurationsaufwand | gering | gering | sehr gering | hoch |

Ausschlaggebend war die Kombination aus **keinen Kosten** und einer
**sauberen Trennung von Geheimnis und Adresse**: Der Bot-Token ist das
Geheimnis und kommt über `ATA_NOTIFICATION_TOKEN`, die Chat-ID ist eine
Adresse ohne Schutzbedarf und steht in `config/default.yaml`. Das passt zur
Geheimnis-Haltung des Projekts, ohne einen zusätzlichen Wert einzuführen, für
den es keine Umgebungsvariable gibt.

**ntfy.sh scheidet aus**, obwohl es technisch am einfachsten wäre: Ohne
Authentifizierung ist der Topic-Name faktisch das Geheimnis, und wer ihn
kennt, liest und schreibt mit. Das widerspricht Doc 10 §13.

**Pushover** wäre fachlich die sauberste Wahl — ein reiner Alarmdienst mit
Prioritätsstufen —, verlangt aber eine Anschaffung je Plattform für einen
Kanal, der im Regelfall nie etwas sendet.

**SMTP** wurde verworfen, weil es die meiste Konfiguration für die
unzuverlässigste Zustellung bringt: Ob eine Mail als Push auf dem Telefon
ankommt, entscheidet die Mail-App, nicht dieses System.

### 2. Der Kanal darf den Lauf nicht abbrechen

Bisher konnte `Notifier.send` nicht scheitern — `LoggingNotifier` schreibt nur
ins Protokoll. Mit einem Netzwerkaufruf ändert sich das, und die Stelle ist
heikel: `_report_overdue` läuft in `_dispatch` **vor** der Entscheidung über
den heutigen Lauf. Ein ungefangener Fehler beim Melden eines *gestrigen*
Ausfalls verhinderte damit die *heutige* Analyse.

Ein Telegram-Ausfall darf den Screener nicht anhalten. Der Anwendungsfall
isoliert Fehler des Kanals deshalb genauso, wie er sie je Aktie isoliert:
`NotifierError` wird gefangen, laut protokolliert — und der Lauf geht weiter.

### 3. Eine nicht zugestellte Meldung gilt als nicht gesendet

Scheitert die Zustellung, wird `mark_alert_sent` **nicht** geschrieben. Der
nächste Start in 15 Minuten versucht es erneut.

Die Alternative — Vermerk setzen und die Meldung verloren geben — wäre
schlechter: Sie erzeugte genau den stillen Ausfall, gegen den dieser Kanal
gebaut wird, eine Ebene höher. Die Kosten sind gering, weil überfällige Läufe
selten sind und der Vermerk bei Erfolg sofort greift.

### 4. Fehlkonfiguration bricht vor dem Lauf ab

`build_notifier` verlangt bei `channel: telegram` sowohl `ATA_NOTIFICATION_TOKEN`
als auch `notifications.telegram.chat_id` und scheitert sonst mit
Rückgabewert 2 — geprüft in `command_dispatch`, **bevor** der halbstündige
Backfill beginnt. Dasselbe Muster wie bei den Anbieter-Geheimnissen.

## Konsequenzen

- Eine externe Abhängigkeit mehr im Tageslauf, aber eine unkritische: Sie wird
  nur im Fehlerfall angefasst, und ihr Ausfall bleibt folgenlos für die
  Analyse.
- Der Bot-Token ist ein Geheimnis wie jedes andere und gehört ausschließlich in
  `ATA_NOTIFICATION_TOKEN`.
- Telegram-Nachrichten verlassen das eigene Netz. Die Meldung enthält deshalb
  bewusst nur Handelstag, Kerzenzeitpunkt und Ursache — **keine Kurse, keine
  Kandidaten, keine Analyseergebnisse.**
- `notifications.channel: pushover` bleibt im Schema und weiterhin unumgesetzt;
  wer es einstellt, bekommt weiter einen klaren Fehler.

## Nicht Gegenstand dieser Entscheidung

- **Die Ergebnis-Benachrichtigung nach jeder Analyse** (Doc 02 §2.12,
  `notifications.send_when_no_candidates`). Sie steht in der Roadmap unter
  Sprint 6 und nutzt denselben Kanal später wieder, ohne ihn erneut zu
  entscheiden.
- **Prioritäten, Wiederholungen, Quittierung.** Eine Meldung je überfälligem
  Lauf genügt; alles Weitere wäre Aufwand für einen Fall, der selten eintritt.

## Nachtrag vom 2026-09-01: `pushover` ist aus dem Schema entfernt

Die Zusicherung oben — „bleibt im Schema und weiterhin unumgesetzt; wer es
einstellt, bekommt weiter einen klaren Fehler" — wird zurückgenommen. Der
Wert ist aus `NotificationsConfig.channel` gestrichen; die Konfiguration
nimmt ihn nicht mehr an.

Das Repository-Audit vom 2026-08-23 führte den Zustand als Risiko R10 und
das [Audit 2](../audits/2026-08-31-repository-audit-2.md) als Maßnahme
A2-M10. Der Grund ist einfach: Eine Einstellung, die das Schema erlaubt und
die Anwendung anschließend zurückweist, ist ein Versprechen ohne Deckung.
Ein klarer Fehler zur Startzeit ist besser als ein später Ausfall, aber
kein Fehler ist besser als beides — und ein zweiter Kanal wird nicht
gebraucht: Telegram trägt seit dem 2026-09-01 den Dauerbetrieb.

Der Absicherungstest, der die Nichtumsetzung festhielt, prüft jetzt das
Gegenstück: Die Konfiguration lehnt den Wert ab. Doc 10 §6.13 nennt Pushover
weiterhin als einen der zwei geprüften Kandidaten — als Auswahlprotokoll ist
das richtig und bleibt stehen.
