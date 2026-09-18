import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Datenzugang, Stand } from '@/components/Datenzugang';
import type { Datenbaum, Manifest } from '@/lib/datenbaum';

const setzeDatenbaum = vi.fn();
const oeffneDatenbaum = vi.fn();
const datenmodus = vi.fn();

vi.mock('@/lib/api', () => ({
  setzeDatenbaum: (...args: unknown[]) => setzeDatenbaum(...args) as unknown,
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
}));

vi.mock('@/lib/datenbaum', () => ({
  datenmodus: () => datenmodus() as unknown,
  oeffneDatenbaum: (...args: unknown[]) => oeffneDatenbaum(...args) as unknown,
}));

const MANIFEST: Manifest = {
  format: 1,
  export_id: 'export-1',
  exported_at: '2026-09-07T21:00:00+00:00',
  run_id: 'lauf-a',
  run_started_at: '2026-09-07T16:45:00+00:00',
  run_completed_at: '2026-09-07T17:20:00+00:00',
  run_status: 'COMPLETED',
  application_version: '0.1.0',
  report_schema_version: 'report-v2',
  signal_rule_version: 'g1',
  symbols: {},
  counts: {},
  stocks_without_chart: [],
  files: {},
};

function baumMit(manifest: Manifest = MANIFEST): Datenbaum {
  return { manifest } as Datenbaum;
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('Im eigenen Netz', () => {
  it('reicht die Kinder unveraendert durch', () => {
    datenmodus.mockReturnValue('api');

    render(
      <Datenzugang>
        <p>Inhalt</p>
      </Datenzugang>,
    );

    expect(screen.getByText('Inhalt')).toBeTruthy();
    // Kein Stand, keine Abfrage: Im eigenen Netz liegt zwischen Oberflaeche
    // und Daten nichts.
    expect(screen.queryByText(/Stand:/)).toBeNull();
    expect(oeffneDatenbaum).not.toHaveBeenCalled();
  });
});

describe('Stufe 1, statischer Datenbaum', () => {
  it('oeffnet den Stand selbst und zeigt danach die Kinder', async () => {
    datenmodus.mockReturnValue('statisch');
    oeffneDatenbaum.mockResolvedValue(baumMit());

    render(
      <Datenzugang>
        <p>Inhalt</p>
      </Datenzugang>,
    );

    await waitFor(() => {
      expect(screen.getByText('Inhalt')).toBeTruthy();
    });
    // Erst anmelden, dann rendern: Sonst riefe eine Ansicht `holen`, bevor
    // der Baum bekannt ist.
    expect(setzeDatenbaum).toHaveBeenCalled();
    expect(screen.getByText(/Stand:/)).toBeTruthy();
  });

  it('zeigt einen Fehler statt einer leeren Ansicht', async () => {
    datenmodus.mockReturnValue('statisch');
    oeffneDatenbaum.mockRejectedValue(new Error('Kein Stand gefunden'));

    render(
      <Datenzugang>
        <p>Inhalt</p>
      </Datenzugang>,
    );

    await waitFor(() => {
      expect(screen.getByText('Kein Stand gefunden')).toBeTruthy();
    });
    expect(screen.queryByText('Inhalt')).toBeNull();
  });
});

describe('Stufe 2, verschluesselter Datenbaum', () => {
  it('fragt nach der Passphrase und zeigt die Kinder noch nicht', () => {
    datenmodus.mockReturnValue('verschluesselt');

    render(
      <Datenzugang>
        <p>Inhalt</p>
      </Datenzugang>,
    );

    expect(screen.getByLabelText('Passphrase')).toBeTruthy();
    expect(screen.queryByText('Inhalt')).toBeNull();
    // Ohne Zutun wird nichts geladen -- die Passphrase kommt vom Menschen.
    expect(oeffneDatenbaum).not.toHaveBeenCalled();
  });

  it('meldet eine falsche Passphrase und bleibt bei der Abfrage', async () => {
    datenmodus.mockReturnValue('verschluesselt');
    oeffneDatenbaum.mockRejectedValue(new Error('Passphrase falsch'));

    render(
      <Datenzugang>
        <p>Inhalt</p>
      </Datenzugang>,
    );
    fireEvent.change(screen.getByLabelText('Passphrase'), { target: { value: 'falsch' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Stand oeffnen' }));

    await waitFor(() => {
      expect(screen.getByText('Passphrase falsch')).toBeTruthy();
    });
    expect(screen.getByLabelText('Passphrase')).toBeTruthy();
    expect(screen.queryByText('Inhalt')).toBeNull();
  });
});

describe('Der Stand', () => {
  it('nennt Lauf und Exportzeitpunkt', () => {
    render(<Stand baum={baumMit()} />);

    expect(screen.getByText(/2026-09-07T17:20/)).toBeTruthy();
    expect(screen.getByText(/2026-09-07T21:00/)).toBeTruthy();
  });

  it('nennt die Aktien ohne Chart', () => {
    // Ohne die Liste saehe eine Aktie ohne Kursreihe im Bestand aus wie eine,
    // deren Datei beim Hochladen verloren ging.
    render(<Stand baum={baumMit({ ...MANIFEST, stocks_without_chart: ['MSFT'] })} />);

    expect(screen.getByText(/ohne Chart: MSFT/)).toBeTruthy();
  });

  it('warnt, wenn der Stand aelter ist als der zuletzt gesehene', () => {
    // Ein vollstaendig zurueckgespielter alter Stand ist in sich stimmig --
    // jede Pruefsumme passt. Zu erkennen ist er nur am Datum.
    window.localStorage.setItem('ata-hoechster-stand', '2026-09-08T09:00:00+00:00');

    render(<Stand baum={baumMit()} />);

    expect(screen.getByText(/aelter als der zuletzt gesehene/)).toBeTruthy();
  });

  it('warnt nicht beim ersten Besuch', () => {
    render(<Stand baum={baumMit()} />);

    expect(screen.queryByText(/aelter als der zuletzt gesehene/)).toBeNull();
    expect(window.localStorage.getItem('ata-hoechster-stand')).toBe(MANIFEST.exported_at);
  });
});
