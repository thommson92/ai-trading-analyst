import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Tagesuebersicht } from '@/components/Tagesuebersicht';
import type { AnalysisRunDetail, ReportSummary } from '@/lib/api';

afterEach(cleanup);

const LAUF: AnalysisRunDetail = {
  id: '2b0f1f7a-0000-0000-0000-000000000001',
  status: 'COMPLETED',
  started_at: '2026-09-01T16:50:00+00:00',
  completed_at: '2026-09-01T17:04:00+00:00',
  number_of_stocks: 192,
  candidates_found: 2,
  error_message: null,
  earnings_excluded: 3,
  earnings_unknown: 0,
  module_errors: 0,
};

function bericht(überschreibung: Partial<ReportSummary>): ReportSummary {
  return {
    report_id: 'r1',
    symbol: 'AAPL',
    created_at: '2026-09-01T17:00:00+00:00',
    recommendation: 'CANDIDATE',
    swing_score: 6.5,
    investment_score: 5.0,
    ...überschreibung,
  };
}

describe('Tagesuebersicht', () => {
  it('zeigt die Kennzahlen des Laufs', () => {
    render(<Tagesuebersicht lauf={LAUF} letzterErfolg={null} kandidaten={[]} />);

    expect(screen.getByText('abgeschlossen')).not.toBeNull();
    expect(screen.getByText('192')).not.toBeNull();
    // Der Earnings-Ausschluss ist eine eigene Zahl, kein Nebensatz.
    expect(screen.getByText('Wegen Berichtstermin ausgeschlossen')).not.toBeNull();
  });

  it('nennt fehlende Erfolgslaeufe beim Namen', () => {
    render(<Tagesuebersicht lauf={LAUF} letzterErfolg={null} kandidaten={[]} />);

    expect(screen.getByText('noch keiner')).not.toBeNull();
  });

  it('meldet einen unbekannten Berichtstermin als Warnung, nicht als Entwarnung', () => {
    render(
      <Tagesuebersicht
        lauf={{ ...LAUF, earnings_unknown: 4 }}
        letzterErfolg={null}
        kandidaten={[]}
      />,
    );

    const warnung = screen.getByText(/kein Berichtstermin bekannt/);
    expect(warnung.textContent).toContain('kein belegter Nichttermin');
  });

  it('sagt ausdruecklich, wenn es nichts zu warnen gibt', () => {
    render(<Tagesuebersicht lauf={LAUF} letzterErfolg={null} kandidaten={[]} />);

    expect(screen.getByText('Keine.')).not.toBeNull();
  });

  it('sortiert die Kandidaten nach Swing-Score und zeigt fehlende Werte als Strich', () => {
    render(
      <Tagesuebersicht
        lauf={LAUF}
        letzterErfolg={null}
        kandidaten={[
          bericht({ report_id: 'r1', symbol: 'OHNE', swing_score: null, recommendation: null }),
          bericht({ report_id: 'r2', symbol: 'STARK', swing_score: 8.2 }),
        ]}
      />,
    );

    const zeilen = screen.getAllByRole('row').slice(1);
    expect(zeilen.map((zeile) => within(zeile).getAllByRole('cell')[0]?.textContent)).toEqual([
      'STARK',
      'OHNE',
    ]);
    const ohneScore = zeilen[1];
    expect(ohneScore).toBeDefined();
    expect(within(ohneScore as HTMLElement).getAllByRole('cell')[2]?.textContent).toBe('–');
  });

  it('sagt es, wenn ein Lauf keinen Kandidaten hervorgebracht hat', () => {
    render(<Tagesuebersicht lauf={LAUF} letzterErfolg={null} kandidaten={[]} />);

    expect(screen.getByText(/keinen Kandidaten/)).not.toBeNull();
  });
});
