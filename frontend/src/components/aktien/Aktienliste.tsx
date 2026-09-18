'use client';

import Link from 'next/link';
import { useState, type ReactNode } from 'react';

import { Empfehlungsbadge } from '@/components/kandidaten/Empfehlungsbadge';
import { Signalbuchstaben } from '@/components/kandidaten/Signalbuchstaben';
import { Tabelle, type Spalte } from '@/components/ui/Tabelle';
import type { Aktieneintrag } from '@/lib/api';
import { formatScore, formatTag } from '@/lib/format';
import { aktieAdresse } from '@/lib/url';

function spalten(
  gesperrt: ReadonlySet<string>,
  ohneChart: ReadonlySet<string>,
): readonly Spalte<Aktieneintrag>[] {
  return [
    {
      schluessel: 'symbol',
      titel: 'Symbol',
      kopf: true,
      render: (a) => <Link href={aktieAdresse(a.symbol)}>{a.symbol}</Link>,
      sortWert: (a) => a.symbol,
    },
    {
      schluessel: 'name',
      titel: 'Unternehmen',
      render: (a) => a.last_report?.company_name ?? '–',
      sortWert: (a) => a.last_report?.company_name,
    },
    {
      schluessel: 'bericht',
      titel: 'Letzter Bericht',
      render: (a) => formatTag(a.last_report?.created_at ?? null),
      sortWert: (a) => a.last_report?.created_at,
    },
    {
      schluessel: 'empfehlung',
      titel: 'Empfehlung',
      render: (a) =>
        a.last_report === null ? '–' : <Empfehlungsbadge stufe={a.last_report.recommendation} />,
      sortWert: (a) => a.last_report?.recommendation,
    },
    {
      schluessel: 'swing',
      titel: 'Swing',
      zahl: true,
      render: (a) => formatScore(a.last_report?.swing_score ?? null),
      sortWert: (a) => a.last_report?.swing_score,
    },
    {
      schluessel: 'investment',
      titel: 'Investment',
      zahl: true,
      render: (a) => formatScore(a.last_report?.investment_score ?? null),
      sortWert: (a) => a.last_report?.investment_score,
    },
    {
      schluessel: 'signale',
      titel: 'Signale',
      render: (a) => <Signalbuchstaben buchstaben={a.last_report?.signal_letters ?? null} />,
    },
    {
      schluessel: 'berichte',
      titel: 'Berichte',
      zahl: true,
      render: (a) => a.reports_count,
      sortWert: (a) => a.reports_count,
    },
    {
      schluessel: 'backtest',
      titel: 'Backtest-Stand',
      render: (a) => formatTag(a.signal_backtest_evaluated_at),
      sortWert: (a) => a.signal_backtest_evaluated_at,
    },
    {
      schluessel: 'stand',
      titel: 'Hinweise',
      render: (a) => (
        <>
          {gesperrt.has(a.symbol) && <span className="badge badge-neutral">gesperrt</span>}
          {ohneChart.has(a.symbol) && <span className="badge badge-warnung">ohne Chart</span>}
        </>
      ),
    },
  ];
}

export function Aktienliste({
  aktien,
  gesperrt,
  ohneChart,
}: {
  aktien: readonly Aktieneintrag[];
  gesperrt: ReadonlySet<string>;
  ohneChart: ReadonlySet<string>;
}): ReactNode {
  const [suche, setSuche] = useState('');
  const begriff = suche.trim().toUpperCase();
  const sichtbar =
    begriff === ''
      ? aktien
      : aktien.filter(
          (a) =>
            a.symbol.includes(begriff) ||
            (a.last_report?.company_name ?? '').toUpperCase().includes(begriff),
        );
  return (
    <>
      <div className="suchzeile">
        <label htmlFor="aktiensuche">Suche</label>
        <input
          id="aktiensuche"
          type="search"
          value={suche}
          placeholder="Symbol oder Unternehmen"
          onChange={(ereignis) => {
            setSuche(ereignis.target.value);
          }}
        />
        <span className="gedaempft">
          {sichtbar.length} von {aktien.length} Aktien
        </span>
      </div>
      <Tabelle
        spalten={spalten(gesperrt, ohneChart)}
        zeilen={sichtbar}
        schluesselVon={(a) => a.symbol}
        sortierung={{ schluessel: 'symbol', richtung: 'auf' }}
        beschriftung="Alle Aktien"
      />
    </>
  );
}
