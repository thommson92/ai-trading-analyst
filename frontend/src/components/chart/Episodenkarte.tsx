import type { ReactNode } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Kennzahl, Kennzahlen } from '@/components/ui/Kennzahl';
import type { BacktestEpisode } from '@/lib/api';
import { formatKurs, formatProzent, formatZeitpunkt } from '@/lib/format';

/**
 * Die gewaehlte Episode: Einstieg, Kombination, und was der Kurs je
 * Horizont danach tat -- die Zahlen, aus denen die Aggregate entstehen.
 */
export function Episodenkarte({
  episode,
  horizont,
  onHorizont,
  onVor,
  onZurueck,
  onSchliessen,
}: {
  episode: BacktestEpisode;
  horizont: number;
  onHorizont: (h: number) => void;
  onVor: (() => void) | null;
  onZurueck: (() => void) | null;
  onSchliessen: () => void;
}): ReactNode {
  return (
    <div className="episodenkarte">
      <div className="episodenkarte-kopf">
        <div>
          <strong>Einstieg {formatZeitpunkt(episode.entry_at)}</strong> zu{' '}
          {formatKurs(episode.entry_close)}
          <span className="gedaempft">
            {' '}
            · Signale {episode.letters} · {episode.trigger_count} Trigger bis{' '}
            {formatZeitpunkt(episode.last_trigger_at)}
          </span>
        </div>
        <div className="episodenkarte-knoepfe">
          <button
            type="button"
            className="knopf-leicht"
            onClick={onZurueck ?? undefined}
            disabled={onZurueck === null}
          >
            ← vorige
          </button>
          <button
            type="button"
            className="knopf-leicht"
            onClick={onVor ?? undefined}
            disabled={onVor === null}
          >
            nächste →
          </button>
          <button type="button" className="knopf-leicht" onClick={onSchliessen}>
            schließen
          </button>
        </div>
      </div>
      <div className="horizontwahl" role="group" aria-label="Horizont">
        {episode.horizons.map((h) => (
          <button
            key={h.horizon}
            type="button"
            className={h.horizon === horizont ? 'knopf-leicht aktiv' : 'knopf-leicht'}
            aria-pressed={h.horizon === horizont}
            onClick={() => {
              onHorizont(h.horizon);
            }}
          >
            {h.horizon} Kerzen
          </button>
        ))}
      </div>
      <Kennzahlen>
        {episode.horizons.map((h) => (
          <Kennzahl
            key={h.horizon}
            label={`Rendite nach ${String(h.horizon)}`}
            wert={
              h.return_pct === null ? (
                <span className="fehlt">nicht erreicht</span>
              ) : (
                <Badge variante={h.return_pct > 0 ? 'gewinn' : 'verlust'}>
                  {formatProzent(h.return_pct, 2)}
                </Badge>
              )
            }
            hinweis={
              h.return_pct === null
                ? undefined
                : `min ${formatProzent(h.max_loss, 2)} · Drawdown ${formatProzent(h.drawdown, 2)} · ${h.held_above_entry === true ? 'stets über Einstieg' : 'zwischenzeitlich darunter'}`
            }
            betont={h.horizon === horizont}
          />
        ))}
      </Kennzahlen>
    </div>
  );
}
