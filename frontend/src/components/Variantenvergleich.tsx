// Grundlinie und gemanagte Variante nebeneinander -- nie verrechnet.
//
// Der Abstand zwischen beiden **ist** die Aussage (ADR 0058, Festlegung 7).
// Sie zu einer Zahl zusammenzuziehen waere derselbe Fehler wie eine
// gemeinsame Erfolgsquote aus Trefferquote und Halten oberhalb des
// Einstiegs (CLAUDE.md).

import type { Konfidenz, VariantenKennzahlen } from '@/lib/api';
import {
  AUSGANG_TEXT,
  KONFIDENZ_TEXT,
  formatGeld,
  formatProzent,
} from '@/lib/format';
import type { Ausgang } from '@/lib/api';

interface Eigenschaften {
  held: VariantenKennzahlen | null;
  managed: VariantenKennzahlen | null;
  konfidenz: Konfidenz;
  trades: number;
}

const AUSGAENGE: readonly Ausgang[] = [
  'EXPIRED_WORTHLESS',
  'ASSIGNED',
  'TAKE_PROFIT',
  'STOPPED_OUT',
  'CLOSED_AT_EXPIRATION',
];

function Zeile({
  name,
  held,
  managed,
}: {
  name: string;
  held: string;
  managed: string;
}): React.ReactElement {
  return (
    <tr>
      <th scope="row">{name}</th>
      <td className="zahl">{held}</td>
      <td className="zahl">{managed}</td>
    </tr>
  );
}

export function Variantenvergleich({
  held,
  managed,
  konfidenz,
  trades,
}: Eigenschaften): React.ReactElement {
  if (held === null || managed === null) {
    // Keine Grundlage heisst: gar keine Zahl, nicht eine niedrige. Die
    // Stichprobengroesse steht trotzdem da -- sie ist die Auskunft.
    return (
      <p className="ohne-grundlage">
        {KONFIDENZ_TEXT[konfidenz]} – {trades}{' '}
        {trades === 1 ? 'Trade' : 'Trades'}. Kennzahlen werden erst ab der
        konfigurierten Mindeststichprobe ausgewiesen.
      </p>
    );
  }
  return (
    <table className="varianten">
      <caption>
        {trades} {trades === 1 ? 'Trade' : 'Trades'} · {KONFIDENZ_TEXT[konfidenz]}
      </caption>
      <thead>
        <tr>
          <th scope="col">Kennzahl</th>
          <th scope="col">gehalten</th>
          <th scope="col">gemanagt</th>
        </tr>
      </thead>
      <tbody>
        <Zeile
          name="Anteil über null"
          held={formatProzent(held.win_rate)}
          managed={formatProzent(managed.win_rate)}
        />
        <Zeile
          name="Rendite auf gebundenes Kapital"
          held={formatProzent(held.mean_return_on_capital, 2)}
          managed={formatProzent(managed.mean_return_on_capital, 2)}
        />
        <Zeile
          name="Ergebnis im Mittel"
          held={formatGeld(held.mean_profit)}
          managed={formatGeld(managed.mean_profit)}
        />
        <Zeile
          name="Ergebnis im Median"
          held={formatGeld(held.median_profit)}
          managed={formatGeld(managed.median_profit)}
        />
        <Zeile
          name="Summe"
          held={formatGeld(held.total_profit)}
          managed={formatGeld(managed.total_profit)}
        />
        {/* Der schlechteste Trade steht fest in der Tabelle und nicht hinter
            einem Aufklappen: Er ist die Zahl, die eine gute Trefferquote
            nicht zeigt. */}
        <Zeile
          name="schlechtester Trade"
          held={formatGeld(held.worst_profit)}
          managed={formatGeld(managed.worst_profit)}
        />
        {AUSGAENGE.map((ausgang) => (
          <Zeile
            key={ausgang}
            name={AUSGANG_TEXT[ausgang]}
            held={String(held.outcomes[ausgang] ?? 0)}
            managed={String(managed.outcomes[ausgang] ?? 0)}
          />
        ))}
      </tbody>
    </table>
  );
}
