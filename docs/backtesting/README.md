# Bildbelege zur Kandidatenregel

Ausschnitte aus dem Validierungschart (`cli chart`), AAPL, 195-Minuten-Kerzen
aus dem Bestand des Servers. Sie sind die Grundlage von
[ADR 0057](../adr/0057-torbedingungen-und-episoden.md) und bleiben als Beleg
liegen — eine Messung, die niemand nachsehen kann, ist keine.

Alle Angaben beziehen sich auf die Regel nach
[ADR 0056](../adr/0056-kaufsignale-und-zusatzkriterien.md), also auf den Stand
**vor** den Torbedingungen.

| Bild | Stelle | Befund |
|---|---|---|
| `Zusammenfassung.png` | 01./02./06.07.2026 | Drei Trigger auf einer Bewegung; sie teilen dieselben Signalereignisse (RSI-Kreuz auf Kerze 741, EMA20-Durchbruch auf 742, EMA-Kreuz auf 744). Bereits vor ADR 0057 **ein** gezähltes Ereignis — der Chart zeigte die rohen Punkte. |
| `Fraglich.png` | 28.08.2026 | Alle drei Kaufsignale feuerten vier Kerzen zuvor; an der Entscheidungskerze kreuzt nichts. Fällt seit ADR 0057 an der Frische. |
| `Negativkerze.png` | 16./17.06.2026 | Unmittelbar vor dem Absturz von 300 auf 275. Der 16.06. trägt eine Kreuzung, die den EMA 20 um 0,04 ATR überschreitet; der 17.06. hat keine frische Kreuzung, ist rot und schließt unter dem EMA 20. Der 17.06. fällt seit ADR 0057, der 16.06. nicht — siehe dort Abschnitt 4. |
| `Gruppierung.png` | 18.–25.08.2026 | Erste drei Trigger wie `Zusammenfassung.png`. Die letzten beiden teilen **kein** Ereignis mit ihnen und sind deshalb eine eigene Episode, nicht ein Nachhall des vorherigen. |
