import type { ReactNode } from 'react';

import { Karte } from '@/components/ui/Karte';
import { Tabelle, type Spalte } from '@/components/ui/Tabelle';
import type { ReportDocument } from '@/lib/api';
import { sichereAdresse } from '@/lib/adresse';
import { beschrifte, formatTag } from '@/lib/format';

import { Vorbehalte } from '../Vorbehalte';
import { feldText, inhaltListe, objektliste, type JsonObjekt } from '../typwaechter';

function Quellenlink({ quelle }: { quelle: JsonObjekt }): ReactNode {
  const url = feldText(quelle, 'url');
  const sicher = sichereAdresse(url);
  const label = feldText(quelle, 'label') ?? url ?? '–';
  // Nur https wird ein Link (ADR 0063, Entscheidung 8); alles andere bleibt Text.
  return sicher === null ? (
    <span>{label}</span>
  ) : (
    <a href={sichereAdresse(url) ?? ''} target="_blank" rel="noopener noreferrer">
      {label}
    </a>
  );
}

const SPALTEN: readonly Spalte<JsonObjekt>[] = [
  {
    schluessel: 'kind',
    titel: 'Art',
    render: (q) => beschrifte((feldText(q, 'kind') ?? '–').toLowerCase()),
    sortWert: (q) => feldText(q, 'kind'),
  },
  { schluessel: 'label', titel: 'Quelle', kopf: true, render: (q) => <Quellenlink quelle={q} /> },
  {
    schluessel: 'url',
    titel: 'Adresse',
    render: (q) => <span className="adresse">{feldText(q, 'url') ?? '–'}</span>,
  },
  {
    schluessel: 'wann',
    titel: 'Abruf / Einreichung',
    render: (q) => formatTag(feldText(q, 'retrieved_at') ?? feldText(q, 'filed')),
    sortWert: (q) => feldText(q, 'retrieved_at') ?? feldText(q, 'filed'),
  },
  { schluessel: 'alter', titel: 'Alter', render: (q) => feldText(q, 'source_age') ?? '–' },
];

export function Quellen({ dokument }: { dokument: ReportDocument }): ReactNode {
  const abschnitt = dokument.abschnitte['QUELLEN'];
  const quellen = objektliste(inhaltListe(abschnitt));
  return (
    <Karte titel="Quellen">
      <Vorbehalte name="QUELLEN" abschnitt={abschnitt} />
      {quellen.length > 0 && (
        <Tabelle
          spalten={SPALTEN}
          zeilen={quellen}
          schluesselVon={(q) => `${feldText(q, 'kind') ?? ''}:${feldText(q, 'url') ?? ''}`}
          beschriftung="Quellen"
        />
      )}
    </Karte>
  );
}
