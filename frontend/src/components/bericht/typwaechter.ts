// Schmale Typwaechter ueber dem rohen Dokument. Sie lesen, sie raten nicht:
// Ein Feld, das nicht die erwartete Form hat, ist null -- und landet dann
// unter "Weitere Felder", statt still zu verschwinden.

import type { Berichtsabschnitt, JsonWert } from '@/lib/api';

export type JsonObjekt = { [schluessel: string]: JsonWert };

export function istObjekt(wert: JsonWert | undefined): wert is JsonObjekt {
  return typeof wert === 'object' && wert !== null && !Array.isArray(wert);
}

export function istListe(wert: JsonWert | undefined): wert is JsonWert[] {
  return Array.isArray(wert);
}

export function feldText(objekt: JsonObjekt | null, schluessel: string): string | null {
  const wert = objekt?.[schluessel];
  return typeof wert === 'string' ? wert : null;
}

export function feldZahl(objekt: JsonObjekt | null, schluessel: string): number | null {
  const wert = objekt?.[schluessel];
  return typeof wert === 'number' ? wert : null;
}

export function feldWahrheit(objekt: JsonObjekt | null, schluessel: string): boolean | null {
  const wert = objekt?.[schluessel];
  return typeof wert === 'boolean' ? wert : null;
}

export function feldObjekt(objekt: JsonObjekt | null, schluessel: string): JsonObjekt | null {
  const wert = objekt?.[schluessel];
  return istObjekt(wert) ? wert : null;
}

export function feldListe(objekt: JsonObjekt | null, schluessel: string): JsonWert[] {
  const wert = objekt?.[schluessel];
  return istListe(wert) ? wert : [];
}

export function textliste(werte: readonly JsonWert[]): string[] {
  return werte.filter((wert): wert is string => typeof wert === 'string');
}

export function objektliste(werte: readonly JsonWert[]): JsonObjekt[] {
  return werte.filter(istObjekt);
}

export function inhaltObjekt(abschnitt: Berichtsabschnitt | undefined): JsonObjekt | null {
  return abschnitt !== undefined && istObjekt(abschnitt.inhalt) ? abschnitt.inhalt : null;
}

export function inhaltListe(abschnitt: Berichtsabschnitt | undefined): JsonWert[] {
  return abschnitt !== undefined && istListe(abschnitt.inhalt) ? abschnitt.inhalt : [];
}
