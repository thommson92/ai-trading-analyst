import type { ReactNode } from 'react';

import { Badge } from '@/components/ui/Badge';
import { Karte } from '@/components/ui/Karte';
import type { ReportDocument } from '@/lib/api';
import { formatProzent } from '@/lib/format';

import { Restfelder } from '../Restfelder';
import { Vorbehalte } from '../Vorbehalte';
import {
  feldObjekt,
  feldText,
  feldZahl,
  inhaltListe,
  inhaltObjekt,
  textliste,
} from '../typwaechter';

function Punkte({
  titel,
  name,
  dokument,
  variante,
}: {
  titel: string;
  name: string;
  dokument: ReportDocument;
  variante: 'gewinn' | 'verlust';
}): ReactNode {
  const abschnitt = dokument.abschnitte[name];
  const punkte = textliste(inhaltListe(abschnitt));
  return (
    <Karte titel={titel} kopf={<Badge variante={variante}>{punkte.length}</Badge>}>
      <Vorbehalte name={name} abschnitt={abschnitt} />
      {punkte.length > 0 && (
        <ul className="liste">
          {punkte.map((punkt) => (
            <li key={punkt}>{punkt}</li>
          ))}
        </ul>
      )}
    </Karte>
  );
}

export function NewsKI({ dokument }: { dokument: ReportDocument }): ReactNode {
  const abschnitt = dokument.abschnitte['NACHRICHTEN'];
  const inhalt = inhaltObjekt(abschnitt);
  const abdeckung = feldObjekt(inhalt, 'abdeckung');
  const belege = feldObjekt(inhalt, 'belege');
  return (
    <>
      <Karte titel="Nachrichten" kopf={<Badge variante="info">KI-Zusammenfassung</Badge>}>
        <Vorbehalte name="NACHRICHTEN" abschnitt={abschnitt} />
        {feldText(inhalt, 'zusammenfassung') !== null && (
          <p className="fliesstext">{feldText(inhalt, 'zusammenfassung')}</p>
        )}
        {(abdeckung !== null || belege !== null) && (
          <p className="gedaempft">
            {belege !== null && (
              <span>
                {feldZahl(belege, 'distinct_sources') ?? '–'} Quellen ·{' '}
                {feldZahl(belege, 'successful_fetches') ?? '–'} Abrufe ·{' '}
                {feldZahl(belege, 'dropped_citations') ?? '–'} verworfene Zitate
              </span>
            )}
            {abdeckung !== null && feldZahl(abdeckung, 'coverage') !== null && (
              <span> · Abdeckung {formatProzent(feldZahl(abdeckung, 'coverage'), 0)}</span>
            )}
          </p>
        )}
        <Restfelder objekt={inhalt} ausser={['zusammenfassung', 'abdeckung', 'belege']} />
      </Karte>
      <div className="zweispaltig">
        <Punkte titel="Chancen" name="CHANCEN" dokument={dokument} variante="gewinn" />
        <Punkte titel="Risiken" name="RISIKEN" dokument={dokument} variante="verlust" />
      </div>
    </>
  );
}
