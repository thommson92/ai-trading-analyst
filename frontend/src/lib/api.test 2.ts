import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError, ERFOLGREICH, listRuns, listStockReports } from '@/lib/api';

interface Aufruf {
  url: string;
}

function antworte(status: number, koerper: unknown): Aufruf[] {
  const aufrufe: Aufruf[] = [];
  vi.stubGlobal('fetch', (url: string) => {
    aufrufe.push({ url });
    return Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(koerper),
    });
  });
  return aufrufe;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const LEERE_SEITE = { items: [], total: 0, limit: 25, offset: 0 };

describe('holen', () => {
  it('wirft bei einer Fehlerantwort, statt etwas Leeres zurueckzugeben', async () => {
    // Die Zusage des Moduls: Eine Oberflaeche, die einen Fehler als leere
    // Liste zeigt, behauptet, es gebe nichts.
    antworte(500, {});

    await expect(listRuns()).rejects.toBeInstanceOf(ApiError);
  });

  it('nennt Status und Pfad im Fehler', async () => {
    antworte(404, {});

    await expect(listRuns()).rejects.toThrow(/404/);
  });
});

describe('listRuns', () => {
  it('haengt jeden Status einzeln an', async () => {
    const aufrufe = antworte(200, LEERE_SEITE);

    await listRuns({ limit: 1, status: ERFOLGREICH });

    expect(aufrufe[0]?.url).toContain('status=COMPLETED');
    expect(aufrufe[0]?.url).toContain('status=PARTIALLY_COMPLETED');
  });

  it('kennt beide Status als erfolgreich', () => {
    // Ein Lauf mit einem isolierten Modulfehler ist abgeschlossen
    // (Doc 10, Paragraph 11) -- sonst stuende dauerhaft "noch keiner" da.
    expect([...ERFOLGREICH].sort()).toEqual(['COMPLETED', 'PARTIALLY_COMPLETED']);
  });

  it('fragt ohne Angaben ohne Parameter', async () => {
    const aufrufe = antworte(200, LEERE_SEITE);

    await listRuns();

    expect(aufrufe[0]?.url).toBe('/api/v1/analysis-runs');
  });
});

describe('listStockReports', () => {
  it('kodiert das Symbol im Pfad', async () => {
    const aufrufe = antworte(200, LEERE_SEITE);

    await listStockReports('BRK B', { limit: 10, offset: 20 });

    expect(aufrufe[0]?.url).toBe('/api/v1/stocks/BRK%20B/reports?limit=10&offset=20');
  });
});
