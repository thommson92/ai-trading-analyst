import type { ReactNode } from 'react';

import { Ergebnisverteilung } from '@/components/Ergebnisverteilung';
import { Messungskopf } from '@/components/Messungskopf';
import { Variantenvergleich } from '@/components/Variantenvergleich';
import { Karte } from '@/components/ui/Karte';
import type { AktienBacktest } from '@/lib/api';
import { AUSGANG_TEXT, formatDatum, formatGeld, formatProzent } from '@/lib/format';

function Tradetabelle({ backtest }: { backtest: AktienBacktest }): ReactNode {
  if (backtest.trades.length === 0) return null;
  return (
    <details className="tradeliste">
      <summary>Alle {backtest.trades.length} simulierten Trades</summary>
      <div className="breit">
        <table>
          <thead>
            <tr>
              <th scope="col">Einstieg</th>
              <th scope="col">Kriterien</th>
              <th scope="col">Kurs</th>
              <th scope="col">Strike</th>
              <th scope="col">Prämie</th>
              <th scope="col">Verfall</th>
              <th scope="col">Kurs am Verfall</th>
              <th scope="col">gehalten</th>
              <th scope="col">gemanagt</th>
            </tr>
          </thead>
          <tbody>
            {backtest.trades.map((trade) => (
              <tr key={`${String(trade.entry_index)}-${String(trade.strike)}`}>
                <td>{formatDatum(trade.entry_date)}</td>
                <td>{trade.letters}</td>
                <td className="zahl">{trade.underlying_at_entry.toFixed(2)}</td>
                <td className="zahl">{trade.strike.toFixed(2)}</td>
                <td className="zahl">{trade.premium.toFixed(2)}</td>
                <td>{formatDatum(trade.expiration)}</td>
                <td className="zahl">{trade.underlying_at_expiration.toFixed(2)}</td>
                <td className="zahl">
                  {formatGeld(trade.held_profit)}
                  <span className="ausgang"> {AUSGANG_TEXT[trade.held_outcome]}</span>
                </td>
                <td className="zahl">
                  {formatGeld(trade.managed_profit)}
                  <span className="ausgang"> {AUSGANG_TEXT[trade.managed_outcome]}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/** Der Optionsbacktest einer Aktie -- unveraendert aus der ersten Fassung, nur in eine Karte gesetzt. */
export function Optionsbacktest({ backtest }: { backtest: AktienBacktest }): ReactNode {
  return (
    <Karte titel="Optionsbacktest">
      {backtest.measurement === null || backtest.pooled === null ? (
        <p className="ohne-grundlage">
          Für diese Aktie liegt keine Messung vor. Der Optionsbacktest ist ein Handlauf (
          <code>python -m ai_trading_analyst.cli options-backtest --provider ibkr</code>) und
          entsteht nicht im Tageslauf.
        </p>
      ) : (
        <>
          <Messungskopf messung={backtest.measurement} />
          <h3>Über alle Signalkombinationen</h3>
          <Variantenvergleich
            held={backtest.pooled.held}
            managed={backtest.pooled.managed}
            konfidenz={backtest.pooled.confidence}
            trades={backtest.pooled.trades}
          />
          <div className="verteilungen">
            <Ergebnisverteilung
              trades={backtest.trades}
              variante="held"
              titel="Einzelergebnisse: gehalten"
            />
            <Ergebnisverteilung
              trades={backtest.trades}
              variante="managed"
              titel="Einzelergebnisse: gemanagt"
            />
          </div>

          <h3>Je Signalkombination</h3>
          {backtest.combinations.length === 0 ? (
            <p className="ohne-grundlage">
              Keine Episode dieser Aktie fiel in eine qualifizierende Kombination.
            </p>
          ) : (
            <div className="breit">
              <table className="kombinationen">
                <thead>
                  <tr>
                    <th scope="col">Kriterien</th>
                    <th scope="col">Episoden</th>
                    <th scope="col">Trades</th>
                    <th scope="col">ohne Trade</th>
                    <th scope="col">Quote gehalten</th>
                    <th scope="col">Quote gemanagt</th>
                    <th scope="col">Rendite gemanagt</th>
                  </tr>
                </thead>
                <tbody>
                  {backtest.combinations.map((kombination) => (
                    <tr key={kombination.letters}>
                      <th scope="row">{kombination.letters}</th>
                      <td className="zahl">{kombination.episodes}</td>
                      <td className="zahl">{kombination.trades}</td>
                      <td className="zahl">{kombination.without_trade}</td>
                      <td className="zahl">{formatProzent(kombination.held?.win_rate ?? null)}</td>
                      <td className="zahl">
                        {formatProzent(kombination.managed?.win_rate ?? null)}
                      </td>
                      <td className="zahl">
                        {formatProzent(kombination.managed?.mean_return_on_capital ?? null, 2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Tradetabelle backtest={backtest} />
        </>
      )}
    </Karte>
  );
}
