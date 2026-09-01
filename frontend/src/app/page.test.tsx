import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import HomePage from '@/app/page';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const LAUF = {
  id: '2b0f1f7a-0000-0000-0000-000000000001',
  status: 'PARTIALLY_COMPLETED',
  started_at: '2026-09-01T16:50:00+00:00',
  completed_at: '2026-09-01T17:04:00+00:00',
  number_of_stocks: 192,
  candidates_found: 0,
  error_message: null,
  earnings_excluded: 3,
  earnings_unknown: 0,
  module_errors: 1,
};

function stubbe(antworten: Record<string, unknown>, status = 200): void {
  vi.stubGlobal('fetch', (url: string) => {
    const treffer = Object.entries(antworten).find(([teil]) => url.includes(teil));
    return Promise.resolve({
      ok: status >= 200 && status < 300 && treffer !== undefined,
      status: treffer === undefined ? 404 : status,
      json: () => Promise.resolve(treffer?.[1] ?? {}),
    });
  });
}

describe('Tagesuebersicht-Seite', () => {
  it('zeigt einen Fehler an, statt eine leere Uebersicht vorzutaeuschen', async () => {
    stubbe({}, 500);

    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('nicht erreichbar');
    });
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('sagt es, wenn es noch keinen Lauf gibt', async () => {
    stubbe({ 'analysis-runs': { items: [], total: 0, limit: 1, offset: 0 } });

    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText(/noch keinen Analyselauf/)).not.toBeNull();
    });
  });

  it('zaehlt einen Lauf mit isoliertem Modulfehler als erfolgreich', async () => {
    // Der Regressionsfall: Frueher fragte die Seite nur nach COMPLETED, und
    // ein einziger Anbieterfehler liess "noch keiner" dauerhaft stehen.
    const seite = { items: [LAUF], total: 1, limit: 1, offset: 0 };
    stubbe({
      'analysis-runs?limit=1': seite,
      [`analysis-runs/${LAUF.id}/reports`]: [],
      [`analysis-runs/${LAUF.id}`]: LAUF,
    });

    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText('teilweise abgeschlossen')).not.toBeNull();
    });
    expect(screen.queryByText('noch keiner')).toBeNull();
  });
});
