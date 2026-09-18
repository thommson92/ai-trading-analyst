import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  Berichtsseite,
  KOPF_ABSCHNITTE,
  REITER_ABSCHNITTE,
  weitereAbschnitte,
} from '@/components/bericht/Berichtsseite';
import type { ReportDocument } from '@/lib/api';

import bericht from '../../lib/__fixtures__/bericht.json';

const DOKUMENT = bericht as unknown as ReportDocument;

const suche = new URLSearchParams();
const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useSearchParams: () => suche,
  useRouter: () => ({ replace }),
  usePathname: () => '/bericht',
}));

afterEach(() => {
  cleanup();
  suche.delete('tab');
  vi.clearAllMocks();
});

describe('Der Kandidatenbericht', () => {
  it('zeigt im Kopf Kurs, Berichtstermin, Put, Empfehlung, Scores und Signale', () => {
    render(<Berichtsseite dokument={DOKUMENT} />);
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('NVDA');
    expect(screen.getAllByText('176,40 $').length).toBeGreaterThan(0);
    expect(screen.getByText('Berichtstermin frei')).toBeTruthy();
    expect(screen.getByText(/Strike 165,00 \$/)).toBeTruthy();
    expect(screen.getByText('Kandidat')).toBeTruthy();
    expect(screen.getByLabelText('Signale ABE')).toBeTruthy();
  });

  it('ordnet jeden bekannten Abschnitt genau einem Reiter zu', () => {
    const zugeordnet = Object.values(REITER_ABSCHNITTE).flat();
    expect(new Set(zugeordnet).size).toBe(zugeordnet.length);
    // Die achtzehn Abschnitte des Schemas: alles ausser den zwei im Kopf.
    const schema = Object.keys(DOKUMENT.abschnitte).filter((n) => n !== 'NEUER_ABSCHNITT');
    for (const name of schema) {
      expect(zugeordnet.includes(name) || KOPF_ABSCHNITTE.includes(name), name).toBe(true);
    }
  });

  it('zeigt einen unbekannten Abschnitt unter Weitere Abschnitte, nicht gar nicht', () => {
    expect(weitereAbschnitte(DOKUMENT)).toEqual(['NEUER_ABSCHNITT']);
    render(<Berichtsseite dokument={DOKUMENT} />);
    fireEvent.click(screen.getByRole('tab', { name: /Weitere Abschnitte/ }));
    expect(screen.getByText(/aus einer spaeteren Fassung/)).toBeTruthy();
  });

  it('zeigt ein unbekanntes Feld unter Weitere Felder', () => {
    render(<Berichtsseite dokument={DOKUMENT} />);
    // Technik ist der erste Reiter; das fremde Feld liegt in der Lage.
    fireEvent.click(screen.getByText(/Weitere Felder/));
    // Zweimal: unter Weitere Felder und im Rohdokument -- beides ist richtig.
    expect(screen.getAllByText('Neues feld aus der zukunft').length).toBeGreaterThan(0);
    expect(screen.getAllByText('42').length).toBeGreaterThan(0);
  });

  it('haelt den Reiter in der Adresse fest', () => {
    render(<Berichtsseite dokument={DOKUMENT} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Optionen' }));
    expect(replace).toHaveBeenCalledWith('?tab=optionen', { scroll: false });
  });

  it('oeffnet den Reiter aus der Adresse', () => {
    suche.set('tab', 'quellen');
    render(<Berichtsseite dokument={DOKUMENT} />);
    expect(screen.getByRole('tab', { name: 'Quellen' }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('link', { name: 'Reuters' }).getAttribute('href')).toBe(
      'https://www.reuters.com/x',
    );
  });
});
