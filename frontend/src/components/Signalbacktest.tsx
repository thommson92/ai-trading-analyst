// Der Signal-Backtest je Kombination und Horizont.
//
// Trefferquote und dauerhaftes Halten oberhalb des Einstiegs stehen
// nebeneinander und werden nirgends zu einer gemeinsamen Erfolgsquote
// verrechnet (CLAUDE.md, "Backtesting"). Sie beantworten zwei verschiedene
// Fragen: ob der Kurs nach dem Horizont höher stand, und ob er dazwischen
// nie darunter fiel.

import type { SignalBacktest } from '@/lib/api';
import { KONFIDENZ_TEXT, formatProzent } from '@/lib/format';

export function Signalbacktest({
  ergebnisse,
}: {
  ergebnisse: readonly SignalBacktest[];
}): React.ReactElement {
  if (ergebnisse.length === 0) {
    return (
      <p className="ohne-grundlage">
        Für diese Aktie liegt kein Signal-Backtest vor. Er entsteht im
        Tageslauf, sobald sie Kandidat war.
      </p>
    );
  }
  return (
    <table className="signalbacktest">
      <thead>
        <tr>
          <th scope="col">Kriterien</th>
          <th scope="col">Horizont</th>
          <th scope="col">Ereignisse</th>
          <th scope="col">Trefferquote</th>
          <th scope="col">Rendite im Mittel</th>
          <th scope="col">größter Verlust</th>
          <th scope="col">durchgehend gehalten</th>
          <th scope="col">Stichprobe</th>
        </tr>
      </thead>
      <tbody>
        {ergebnisse.flatMap((ergebnis) =>
          ergebnis.horizons.map((horizont, index) => (
            <tr key={`${ergebnis.letters}-${String(horizont.horizon)}`}>
              {index === 0 && (
                <th scope="row" rowSpan={ergebnis.horizons.length}>
                  {ergebnis.letters}
                </th>
              )}
              <td className="zahl">{horizont.horizon}</td>
              {/* Roh und gezählt beide: Der Unterschied ist die Episodenbildung
                  (ADR 0057), und nur eine der beiden Zahlen zu zeigen ließe
                  offen, worauf die Quote steht. */}
              <td className="zahl">
                {horizont.deduplicated_event_count} von {horizont.raw_event_count}
              </td>
              <td className="zahl">{formatProzent(horizont.hit_rate)}</td>
              <td className="zahl">{formatProzent(horizont.mean_return, 2)}</td>
              <td className="zahl">{formatProzent(horizont.max_loss, 2)}</td>
              <td className="zahl">{formatProzent(horizont.held_above_entry_rate)}</td>
              <td>{KONFIDENZ_TEXT[horizont.confidence]}</td>
            </tr>
          )),
        )}
      </tbody>
    </table>
  );
}
