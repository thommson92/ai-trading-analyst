import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Variantenvergleich } from '@/components/Variantenvergleich';
import type { VariantenKennzahlen } from '@/lib/api';

afterEach(cleanup);

function kennzahlen(
  überschreibung: Partial<VariantenKennzahlen> = {},
): VariantenKennzahlen {
  return {
    trades: 12,
    win_rate: 0.75,
    mean_profit: 41.5,
    median_profit: 38,
    total_profit: 498,
    worst_profit: -260,
    mean_return_on_capital: 0.0042,
    outcomes: {
      EXPIRED_WORTHLESS: 9,
      ASSIGNED: 3,
      TAKE_PROFIT: 0,
      STOPPED_OUT: 0,
      CLOSED_AT_EXPIRATION: 0,
    },
    ...überschreibung,
  };
}

describe('Variantenvergleich', () => {
  it('stellt beide Varianten nebeneinander, ohne sie zu verrechnen', () => {
    render(
      <Variantenvergleich
        held={kennzahlen()}
        managed={kennzahlen({ win_rate: 0.9, mean_return_on_capital: 0.0031 })}
        konfidenz="NORMAL"
        trades={12}
      />,
    );

    expect(screen.getByText('gehalten')).not.toBeNull();
    expect(screen.getByText('gemanagt')).not.toBeNull();
    expect(screen.getByText('75.0 %')).not.toBeNull();
    expect(screen.getByText('90.0 %')).not.toBeNull();
  });

  it('zeigt den schlechtesten Trade offen und nicht hinter einem Aufklappen', () => {
    // Er ist die Zahl, die eine gute Trefferquote nicht zeigt (ADR 0058).
    render(
      <Variantenvergleich
        held={kennzahlen()}
        managed={kennzahlen()}
        konfidenz="NORMAL"
        trades={12}
      />,
    );

    expect(screen.getByText('schlechtester Trade')).not.toBeNull();
    expect(screen.getAllByText('−260,00 $').length).toBe(2);
  });

  it('nennt ohne Grundlage die Stichprobe statt einer Zahl', () => {
    // Keine Grundlage heißt gar keine Zahl, nicht eine niedrige. Eine 0 %
    // wäre die schlechteste Quote statt einer fehlenden.
    render(
      <Variantenvergleich held={null} managed={null} konfidenz="INSUFFICIENT_DATA" trades={4} />,
    );

    expect(screen.getByText(/zu wenig Daten/)).not.toBeNull();
    expect(screen.getByText(/4 Trades/)).not.toBeNull();
    expect(screen.queryByText('0.0 %')).toBeNull();
  });

  it('zählt jeden Ausgang auf, auch die Glattstellung am Verfall', () => {
    // Sie kam mit dem Nachtrag zu Festlegung 7 dazu. Fehlte sie in der
    // Aufzählung, summierten sich die gezeigten Ausgänge nicht auf die
    // Trades -- und die Differenz sähe aus wie ein Rundungsfehler.
    render(
      <Variantenvergleich
        held={kennzahlen()}
        managed={kennzahlen({
          outcomes: {
            EXPIRED_WORTHLESS: 6,
            ASSIGNED: 0,
            TAKE_PROFIT: 4,
            STOPPED_OUT: 1,
            CLOSED_AT_EXPIRATION: 1,
          },
        })}
        konfidenz="NORMAL"
        trades={12}
      />,
    );

    expect(screen.getByText('am Verfall glattgestellt')).not.toBeNull();
  });
});
