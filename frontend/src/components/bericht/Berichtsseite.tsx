'use client';

// Der Kandidatenbericht (ADR 0063, Entscheidung 7): ein Kopf mit dem, was
// zaehlt, darunter Reiter je Themenfeld. Jeder Abschnitt hat eine eigene
// Darstellung; was sie nicht kennt, steht unter "Weitere Felder", und ein
// Abschnitt, den keine Darstellung kennt, unter "Weitere Abschnitte" -- als
// generischer Baum. Nichts verschwindet still.

import { useRouter, useSearchParams } from 'next/navigation';
import type { ReactNode } from 'react';

import { Abschnitt, Berichtsdokument } from '@/components/Berichtsdokument';
import { Berichtskopf } from '@/components/bericht/Berichtskopf';
import { Analysten } from '@/components/bericht/abschnitte/Analysten';
import { Backtest } from '@/components/bericht/abschnitte/Backtest';
import { Bewertung } from '@/components/bericht/abschnitte/Bewertung';
import { Fundamental } from '@/components/bericht/abschnitte/Fundamental';
import { NewsKI } from '@/components/bericht/abschnitte/NewsKI';
import { Optionen } from '@/components/bericht/abschnitte/Optionen';
import { Quellen } from '@/components/bericht/abschnitte/Quellen';
import { Technik } from '@/components/bericht/abschnitte/Technik';
import { Aufklapper } from '@/components/ui/Aufklapper';
import { Reiter, type Reiterdefinition } from '@/components/ui/Reiter';
import type { ReportDocument } from '@/lib/api';

/** Welcher Reiter welche Abschnitte zeigt -- alles Uebrige ist "Weitere". */
export const REITER_ABSCHNITTE: Record<string, readonly string[]> = {
  technik: ['TECHNISCHE_SIGNALE', 'TECHNISCHE_LAGE', 'ZONEN'],
  bewertung: ['SWING_SCORE', 'INVESTMENT_SCORE', 'EMPFEHLUNG', 'KONFIDENZ_UND_DATENLUECKEN'],
  fundamental: ['FUNDAMENTALE_BEWERTUNG'],
  analysten: ['ANALYSTENMEINUNGEN'],
  news: ['NACHRICHTEN', 'CHANCEN', 'RISIKEN'],
  backtest: ['SIGNALSTATISTIK'],
  optionen: ['PUT_STRATEGIEN'],
  quellen: ['QUELLEN'],
};

/** Im Kopf verarbeitet, in keinem Reiter noetig. */
export const KOPF_ABSCHNITTE: readonly string[] = [
  'SYMBOL_UND_UNTERNEHMEN',
  'ANALYSEZEITPUNKT',
  'EARNINGS_STATUS',
];

const REITER: readonly Reiterdefinition[] = [
  { id: 'technik', titel: 'Technik' },
  { id: 'bewertung', titel: 'Bewertung' },
  { id: 'fundamental', titel: 'Fundamental' },
  { id: 'analysten', titel: 'Analysten' },
  { id: 'news', titel: 'News und KI' },
  { id: 'backtest', titel: 'Backtest' },
  { id: 'optionen', titel: 'Optionen' },
  { id: 'quellen', titel: 'Quellen' },
];

export function weitereAbschnitte(dokument: ReportDocument): string[] {
  const bekannt = new Set([...KOPF_ABSCHNITTE, ...Object.values(REITER_ABSCHNITTE).flat()]);
  return Object.keys(dokument.abschnitte).filter((name) => !bekannt.has(name));
}

function Reiterinhalt({ id, dokument }: { id: string; dokument: ReportDocument }): ReactNode {
  switch (id) {
    case 'technik':
      return <Technik dokument={dokument} />;
    case 'bewertung':
      return <Bewertung dokument={dokument} />;
    case 'fundamental':
      return <Fundamental dokument={dokument} />;
    case 'analysten':
      return <Analysten dokument={dokument} />;
    case 'news':
      return <NewsKI dokument={dokument} />;
    case 'backtest':
      return <Backtest dokument={dokument} />;
    case 'optionen':
      return <Optionen dokument={dokument} />;
    case 'quellen':
      return <Quellen dokument={dokument} />;
    case 'weitere':
      return (
        <>
          {weitereAbschnitte(dokument).map((name) => {
            const abschnitt = dokument.abschnitte[name];
            return abschnitt === undefined ? null : (
              <Abschnitt key={name} name={name} abschnitt={abschnitt} />
            );
          })}
        </>
      );
    default:
      return null;
  }
}

export function Berichtsseite({ dokument }: { dokument: ReportDocument }): ReactNode {
  const suche = useSearchParams();
  const router = useRouter();
  const weitere = weitereAbschnitte(dokument);
  const reiter =
    weitere.length === 0
      ? REITER
      : [...REITER, { id: 'weitere', titel: 'Weitere Abschnitte', zusatz: weitere.length }];
  const gewuenscht = suche.get('tab');
  const aktiv = reiter.some((r) => r.id === gewuenscht) ? (gewuenscht ?? 'technik') : 'technik';

  function wechseln(id: string): void {
    const neu = new URLSearchParams(suche.toString());
    neu.set('tab', id);
    router.replace(`?${neu.toString()}`, { scroll: false });
  }

  return (
    <>
      <Berichtskopf dokument={dokument} />
      <Reiter reiter={reiter} aktiv={aktiv} onWechsel={wechseln} beschriftung="Berichtsabschnitte">
        <Reiterinhalt id={aktiv} dokument={dokument} />
      </Reiter>
      <Aufklapper zusammenfassung="Rohdokument (alle achtzehn Abschnitte)">
        <Berichtsdokument dokument={dokument} />
      </Aufklapper>
    </>
  );
}
