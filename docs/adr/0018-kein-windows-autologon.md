# ADR 0018: Kein Windows-Autologon — manueller Start wird akzeptiert

- Status: Angenommen
- Datum: 2026-08-13

## Kontext

Die TWS läuft auf einem Windows-Server und braucht eine **angemeldete
Benutzersitzung**. Einschränkung E2 aus
[ADR 0014](0014-ibkr-produktivintegration-freigegeben.md) hält fest, dass
nach einem Neustart des Servers oder der TWS ein manueller Start
beziehungsweise Login nötig ist — es gibt kein Autologon, kein IB Gateway
und kein IBC.

Praktisch heißt das: Startet der Server sonntagnachts neu, liefert der
Analyzer bis zum manuellen Start am Montag keine Daten.

Die Frage war seit dem TradingView-Spike offen und in ADR 0014 ausdrücklich
als „eigenständige, weiterhin **nicht getroffene** Entscheidung" geführt.

## Entscheidung

**Es wird kein Windows-Autologon eingerichtet.** Der Projektinhaber
akzeptiert, dass er sich nach dem sonntäglichen Neustart im Laufe des
Montags auf den Server schaltet und TWS sowie Analyzer manuell startet.

Das ist eine bewusste Betriebsentscheidung, keine Verschiebung.

## Begründung

Windows-Autologon bedeutet, dass beim Hochfahren **automatisch eine
angemeldete Sitzung existiert**. Wer physischen oder Remote-Zugriff auf die
Maschine erlangt, steht damit vor einem offenen Desktop — mit einer
laufenden TWS, die an derselben Instanz auch von der Trade Automation
Toolbox für echte Orderübermittlung genutzt wird.

Dem steht ein Gewinn an Bequemlichkeit gegenüber: ein manueller Handgriff
pro Woche. Das Verhältnis rechtfertigt das Risiko nicht.

Fachlich ist die Nichtverfügbarkeit verkraftbar. Der Screener wertet
ausschließlich **abgeschlossene** Kerzen aus; ein Montagvormittag ohne Lauf
bedeutet, dass die Kerzen dieses Vormittags später nachgeholt werden — und
genau dafür ist der historische Backfill gebaut, der den letzten Datenstand
kennt und die Lücke füllt.

## Konsequenzen

- **Die Anwendung behandelt eine nicht erreichbare TWS als normalen
  Betriebszustand**, nicht als Störung: klarer Fehler, keine erfundenen
  Daten, kein stiller Ersatzwert. Das ist bereits umgesetzt.
- Der Backfill muss **beliebig große Lücken** schließen können, nicht nur
  den letzten Tag. Ein verlängertes Wochenende oder ein Serverausfall über
  eine Woche darf keinen Sonderfall darstellen.
- **Ändert sich die Betriebslage** — etwa weil der Server keine
  automatischen Neustarts mehr durchführt —, meldet der Projektinhaber das,
  und die Festlegung wird in einem neuen ADR nachgezogen. Dieses wird nicht
  rückwirkend geändert.
- Ein Verzicht auf Autologon schließt andere Wege nicht aus, die **ohne**
  automatische Anmeldung auskommen. Sie sind hier nicht geprüft und wären
  ein eigenes ADR.
