// Die Annahmen einer Messung -- sichtbar, nicht im Kleingedruckten.
//
// Jede Zahl des Optionsbacktests ist eine Modellzahl: Die Praemie ist
// gerechnet, der Verfallskalender konstruiert, das Strike-Raster angenommen
// (ADR 0058). Zwei Messungen desselben Tages unterscheiden sich **nur** in
// diesen Annahmen. Sie gehoeren deshalb ueber die Zahlen und nicht darunter.

import type { Messung } from '@/lib/api';
import { formatDatum, formatZeitpunkt } from '@/lib/format';

const ANNAHME_TEXT: Record<string, string | undefined> = {
  version: 'Verfahrensversion',
  kalender: 'Verfallskalender',
  strike_raster: 'Strike-Raster',
  volatilitaetsfenster: 'Volatilitätsfenster',
  volatilitaetsaufschlag: 'Volatilitätsaufschlag',
  zinssatz: 'Zinssatz',
  ausfuehrungsabschlag: 'Ausführungsabschlag',
  gewinnmitnahme: 'Gewinnmitnahme',
  rueckkauf: 'Rückkauf',
  ziel_delta: 'Ziel-Delta',
};
// Offene Zuordnung mit Rueckfall auf den rohen Schluessel: Eine neue Annahme
// soll sichtbar sein -- notfalls unschoen --, statt aus der Anzeige zu
// verschwinden, weil hier eine Zeile fehlt.

export function Messungskopf({ messung }: { messung: Messung }): React.ReactElement {
  return (
    <section className="messungskopf">
      <p className="modellhinweis">
        Alle Prämien sind <strong>modelliert</strong>. Historische
        Optionsnotierungen gibt es nicht; was der Kurs tat, ist gemessen, was
        die Option einbrachte, ist eine Annahme.
      </p>
      <dl className="annahmen">
        <div>
          <dt>Gemessen am</dt>
          <dd>{formatZeitpunkt(messung.measured_at)}</dd>
        </div>
        <div>
          <dt>Aktien</dt>
          <dd>{messung.stocks}</dd>
        </div>
        <div>
          <dt>Zeitraum</dt>
          <dd>
            {formatDatum(messung.history_start)} bis {formatDatum(messung.history_end)}
          </dd>
        </div>
        <div>
          <dt>Signalregel</dt>
          <dd>{messung.signal_rule_version}</dd>
        </div>
        {Object.entries(messung.assumptions).map(([schluessel, wert]) => (
          <div key={schluessel}>
            <dt>{ANNAHME_TEXT[schluessel] ?? schluessel}</dt>
            <dd>{wert}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
