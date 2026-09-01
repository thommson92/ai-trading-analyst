// Der gespeicherte Bericht, angezeigt wie er ist.
//
// Bewusst allgemein und nicht Abschnitt fuer Abschnitt -- dieselbe
// Ueberlegung wie bei der Konsolenausgabe (``presentation/report_text.py``):
// Eine handgeschriebene Darstellung je Abschnitt veraltete beim naechsten
// neuen Feld still, und das Dashboard zeigte dann weniger, als der Bericht
// enthaelt.

import type { ReactNode } from 'react';

import type { Berichtsabschnitt, JsonWert, ReportDocument } from '@/lib/api';
import { ABSCHNITT_TEXT, beschrifte, formatZeitpunkt } from '@/lib/format';

function Wert({ wert }: { wert: JsonWert }): ReactNode {
  if (wert === null) {
    // Ein Strich, keine leere Zelle: Der Bericht sagt ausdruecklich, dass
    // hier nichts steht.
    return <span className="fehlt">–</span>;
  }
  if (typeof wert === 'boolean') {
    return <span>{wert ? 'ja' : 'nein'}</span>;
  }
  if (typeof wert === 'number' || typeof wert === 'string') {
    return <span>{String(wert)}</span>;
  }
  if (Array.isArray(wert)) {
    if (wert.length === 0) {
      return <span className="fehlt">leer</span>;
    }
    return (
      <ul className="liste">
        {wert.map((eintrag, stelle) => (
          <li key={stelle}>
            <Wert wert={eintrag} />
          </li>
        ))}
      </ul>
    );
  }
  const felder = Object.entries(wert);
  if (felder.length === 0) {
    // Wie bei der leeren Liste: Ein Objekt ohne Felder waere sonst gar nichts
    // zu sehen -- und "nichts zu sehen" liest sich wie "nicht vorhanden".
    return <span className="fehlt">leer</span>;
  }
  return (
    <dl className="felder">
      {felder.map(([schluessel, inhalt]) => (
        <div key={schluessel}>
          <dt>{beschrifte(schluessel)}</dt>
          <dd>
            <Wert wert={inhalt} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Abschnitt({ name, abschnitt }: { name: string; abschnitt: Berichtsabschnitt }): ReactNode {
  return (
    <section className="abschnitt">
      <h3>
        {abschnitt.nummer}. {ABSCHNITT_TEXT[name] ?? name}
        {!abschnitt.verfuegbar && <span className="fehlt"> — nicht verfügbar</span>}
      </h3>
      {abschnitt.vorbehalte.map((vorbehalt, stelle) => (
        <p className="vorbehalt" key={stelle}>
          [{vorbehalt.art}] {vorbehalt.grund}
        </p>
      ))}
      {abschnitt.inhalt !== null && <Wert wert={abschnitt.inhalt} />}
    </section>
  );
}

export function Berichtsdokument({ dokument }: { dokument: ReportDocument }): ReactNode {
  const abschnitte = Object.entries(dokument.abschnitte).sort(
    ([, links], [, rechts]) => links.nummer - rechts.nummer,
  );
  return (
    <>
      <p className="herkunft">
        Bericht {dokument.berichtsschema_version}, Anwendung {dokument.anwendungsversion},
        Signalregel {dokument.signalregel_version}
        {dokument.scoring_version !== null && `, Scoring ${dokument.scoring_version}`} — erstellt{' '}
        {formatZeitpunkt(dokument.erstellt_am)}
      </p>
      {abschnitte.map(([name, abschnitt]) => (
        <Abschnitt key={name} name={name} abschnitt={abschnitt} />
      ))}
    </>
  );
}
