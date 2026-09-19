import { describe, expect, it } from 'vitest';

import { aktieAdresse, berichtAdresse, laufAdresse } from '@/lib/url';

describe('Die Adressen des Dashboards', () => {
  it('halten die Form, die auch die Ergebnismeldung nennt', () => {
    // Vertrag mit backend/.../domain/report/notification.py (ADR 0065):
    // Die Meldung schreibt `laeufe/?id=<lauf>` an die Adresse des Dashboards.
    expect(laufAdresse('abc')).toBe('/laeufe/?id=abc');
  });

  it('kodieren Parameter und beginnen mit einem konstanten Pfad', () => {
    expect(berichtAdresse('a b')).toBe('/bericht/?id=a%20b');
    expect(aktieAdresse('BRK B', { lauf: 'l1', episode: '2025-03-06T14:30:00+00:00' })).toBe(
      '/aktie/?symbol=BRK+B&lauf=l1&episode=2025-03-06T14%3A30%3A00%2B00%3A00',
    );
    expect(aktieAdresse('AAPL', { messung: 'm/1' })).toBe('/aktie/?symbol=AAPL&messung=m%2F1');
  });
});
