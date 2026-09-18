import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { anderesThema, liesThema, speichereThema, wendeThemaAn } from '@/lib/thema';

beforeEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset['thema'];
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('Die gemerkte Wahl', () => {
  it('ist dunkel, solange nichts gemerkt ist', () => {
    expect(liesThema()).toBe('dunkel');
  });

  it('kommt nach dem Speichern zurueck', () => {
    speichereThema('hell');
    expect(liesThema()).toBe('hell');
  });

  it('faellt bei einem fremden Wert auf den Standard zurueck', () => {
    // Ein Wert aus einer aelteren Fassung oder von Hand gesetzt: kein
    // Grund, die Seite ohne Design zu lassen.
    window.localStorage.setItem('ata-thema', 'sepia');
    expect(liesThema()).toBe('dunkel');
  });

  it('kommt ohne Speicher aus', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('gesperrt');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('gesperrt');
    });

    expect(liesThema()).toBe('dunkel');
    expect(() => {
      speichereThema('hell');
    }).not.toThrow();
  });
});

describe('Das Attribut am Wurzelelement', () => {
  it('traegt nur die Abweichung vom Standard', () => {
    wendeThemaAn('hell');
    expect(document.documentElement.dataset['thema']).toBe('hell');

    wendeThemaAn('dunkel');
    expect(document.documentElement.dataset['thema']).toBeUndefined();
  });
});

describe('Der Wechsel', () => {
  it('kennt genau zwei Seiten', () => {
    expect(anderesThema('dunkel')).toBe('hell');
    expect(anderesThema('hell')).toBe('dunkel');
  });
});
