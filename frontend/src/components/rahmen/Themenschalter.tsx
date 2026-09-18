'use client';

import { useEffect, useState, type ReactNode } from 'react';

import {
  STANDARDTHEMA,
  anderesThema,
  liesThema,
  speichereThema,
  wendeThemaAn,
  type Thema,
} from '@/lib/thema';

const BESCHRIFTUNG: Record<Thema, string> = {
  dunkel: 'Helles Design',
  hell: 'Dunkles Design',
};

/**
 * Ein Knopf, der zwischen dunkel und hell wechselt.
 *
 * Er zeigt, wohin er fuehrt, nicht wo man ist -- das sieht der Leser ohnehin.
 * Beim ersten Bild gilt der Standard; die gemerkte Wahl greift im Effekt,
 * sobald der Browser den Speicher hergibt.
 */
export function Themenschalter(): ReactNode {
  const [thema, setThema] = useState<Thema>(STANDARDTHEMA);

  useEffect(() => {
    const gemerkt = liesThema();
    wendeThemaAn(gemerkt);
    setThema(gemerkt);
  }, []);

  function wechseln(): void {
    const naechstes = anderesThema(thema);
    wendeThemaAn(naechstes);
    speichereThema(naechstes);
    setThema(naechstes);
  }

  return (
    <button type="button" className="knopf-leicht" onClick={wechseln}>
      {BESCHRIFTUNG[thema]}
    </button>
  );
}
