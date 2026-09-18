import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Seitenrahmen } from '@/components/rahmen/Seitenrahmen';

const usePathname = vi.fn<() => string>();

vi.mock('next/navigation', () => ({
  usePathname: () => usePathname(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('Der Seitenrahmen', () => {
  it('zeigt Navigation, Stand und Inhalt', () => {
    usePathname.mockReturnValue('/backtests');

    render(
      <Seitenrahmen stand={<p>Stand: heute</p>}>
        <main>Inhalt</main>
      </Seitenrahmen>,
    );

    expect(screen.getByRole('navigation', { name: 'Hauptnavigation' })).toBeTruthy();
    expect(screen.getByText('Stand: heute')).toBeTruthy();
    expect(screen.getByText('Inhalt')).toBeTruthy();
  });

  it('markiert den aktuellen Bereich, mit und ohne Schraegstrich', () => {
    usePathname.mockReturnValue('/backtests');

    render(
      <Seitenrahmen>
        <main>Inhalt</main>
      </Seitenrahmen>,
    );

    const aktiv = screen.getByRole('link', { name: 'Backtests' });
    expect(aktiv.getAttribute('aria-current')).toBe('page');
    // Die Uebersicht ist nicht aktiv -- '/' ist kein Praefix-Treffer.
    expect(screen.getByRole('link', { name: 'Übersicht' }).getAttribute('aria-current')).toBeNull();
  });

  it('klappt die Leiste per Menueknopf auf und per Escape wieder zu', () => {
    usePathname.mockReturnValue('/');

    const { container } = render(
      <Seitenrahmen>
        <main>Inhalt</main>
      </Seitenrahmen>,
    );
    const rahmen = container.querySelector('.rahmen');
    const menue = screen.getByRole('button', { name: 'Menü' });

    expect(rahmen?.getAttribute('data-leiste-offen')).toBe('false');
    fireEvent.click(menue);
    expect(rahmen?.getAttribute('data-leiste-offen')).toBe('true');
    expect(menue.getAttribute('aria-expanded')).toBe('true');

    // Der Fokus ist in der Leiste, solange sie offen ist ...
    expect(document.activeElement?.closest('.seitenleiste')).not.toBeNull();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(rahmen?.getAttribute('data-leiste-offen')).toBe('false');
    // ... und danach wieder auf dem Knopf, nicht irgendwo.
    expect(document.activeElement).toBe(menue);
  });

  it('schliesst die Leiste, wenn ein Bereich gewaehlt wird', () => {
    usePathname.mockReturnValue('/');

    const { container } = render(
      <Seitenrahmen>
        <main>Inhalt</main>
      </Seitenrahmen>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Menü' }));
    fireEvent.click(screen.getByRole('link', { name: 'Backtests' }));

    expect(container.querySelector('.rahmen')?.getAttribute('data-leiste-offen')).toBe('false');
  });
});
