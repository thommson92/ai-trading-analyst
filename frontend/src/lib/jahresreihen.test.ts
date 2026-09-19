// Die Umformung der Jahresreihen (ADR 0067). Geprueft wird vor allem, was
// **nicht** entsteht: keine Einheit ohne Zahl, kein Jahr ohne Beleg, keine
// Waehrung ueber einem gemischten Bild.

import { describe, expect, it } from 'vitest';

import type { JsonObjekt } from '@/components/bericht/typwaechter';
import { berichtsjahre, hatHistorie, reihenAusDokument } from '@/lib/jahresreihen';

import bericht from './__fixtures__/bericht.json';

const DOKUMENT = bericht as unknown as {
  abschnitte: Record<string, { inhalt: JsonObjekt } | undefined>;
};
const INHALT = DOKUMENT.abschnitte['FUNDAMENTALE_BEWERTUNG']?.inhalt ?? null;

describe('Die Jahresreihen aus dem Dokument', () => {
  it('gruppiert nach Einheit und behaelt die Jahre in Reihenfolge', () => {
    const reihen = reihenAusDokument(INHALT);

    expect(reihen.map((r) => r.einheit)).toEqual(['CURRENCY', 'FRACTION', 'RATIO']);
    const betraege = reihen[0];
    expect(betraege?.namen).toEqual(['REVENUE', 'NET_INCOME']);
    expect(betraege?.punkte.map((p) => p.jahr)).toEqual([2022, 2023, 2024, 2025]);
    expect(betraege?.punkte[3]?.werte['REVENUE']).toBe(130500000000);
    expect(betraege?.waehrung).toBe('USD');
  });

  it('nennt keine Waehrung, wo die Einheit keine traegt', () => {
    const margen = reihenAusDokument(INHALT).find((r) => r.einheit === 'FRACTION');

    expect(margen?.waehrung).toBeNull();
    expect(margen?.namen).toEqual(['GROSS_MARGIN', 'NET_MARGIN']);
  });

  it('laesst ein fehlendes Jahr fehlen, statt es zu fuellen', () => {
    // Das Jahr steht in der Reihe, der Wert nicht. Eine durchgezogene Linie
    // ueber diese Luecke waere eine Erfindung.
    const inhalt: JsonObjekt = {
      history: [
        { period_end: '2023-12-31', metrics: [{ name: 'REVENUE', value: 10, unit: 'CURRENCY' }] },
        { period_end: '2024-12-31', metrics: [{ name: 'NET_INCOME', value: 2, unit: 'CURRENCY' }] },
      ],
    };
    const [reihe] = reihenAusDokument(inhalt);

    expect(reihe?.punkte[0]?.werte['NET_INCOME']).toBeUndefined();
    expect(reihe?.punkte[1]?.werte['REVENUE']).toBeUndefined();
    expect(reihe?.namen).toEqual(['REVENUE', 'NET_INCOME']);
  });

  it('gibt ohne Historie nichts zurueck -- und sagt es', () => {
    expect(reihenAusDokument({ fiscal_years: [2024] })).toEqual([]);
    expect(hatHistorie({ fiscal_years: [2024] })).toBe(false);
    expect(hatHistorie(null)).toBe(false);
    expect(hatHistorie(INHALT)).toBe(true);
  });

  it('ueberspringt Eintraege ohne lesbares Jahr', () => {
    const inhalt: JsonObjekt = {
      history: [
        { period_end: 'unbekannt', metrics: [{ name: 'REVENUE', value: 1, unit: 'CURRENCY' }] },
        { period_end: '2024-12-31', metrics: [{ name: 'REVENUE', value: 2, unit: 'CURRENCY' }] },
      ],
    };

    expect(reihenAusDokument(inhalt)[0]?.punkte.map((p) => p.jahr)).toEqual([2024]);
  });

  it('liest die Geschaeftsjahre des Kopfes', () => {
    expect(berichtsjahre(INHALT)).toEqual([2022, 2023, 2024, 2025]);
    expect(berichtsjahre({})).toEqual([]);
  });
});
