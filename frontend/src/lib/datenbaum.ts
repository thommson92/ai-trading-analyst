// Der Datenbaum des Dashboards ausserhalb des Servers (ADR 0060).
//
// Draussen gibt es keine API: Dort liegen Dateien, die der Server nach jedem
// Lauf hinaufgeladen hat. Dieses Modul liest sie -- in Stufe 2 verschluesselt,
// mit einer Passphrase, die den Browser nie verlaesst.
//
// **Das Verfahren ist eine Eigenschaft des Builds.** Welcher Modus gilt,
// entscheidet eine Variable, die Next zur Bauzeit in das Bundle schreibt --
// nicht das Manifest und keine andere Datei, die neben den Daten liegt. Wer
// beim Anbieter schreiben darf, kann damit keinen Klartextmodus einschalten;
// er muesste das Bundle selbst austauschen, und dann besaesse er die Seite
// ohnehin (Bedrohung T21, und der Restrisiko-Eintrag dazu).
//
// Hier steht keine Fachlogik, genau wie in `api.ts`: gerechnet, bewertet und
// eingestuft wird ausschliesslich im Backend. Was hier geschieht, ist Laden,
// Entschluesseln, Pruefen.

export type Datenmodus = 'api' | 'statisch' | 'verschluesselt';

const MINDEST_ITERATIONEN = 600_000;
const ERWARTETES_FORMAT = 1;
const ERWARTETE_KDF = 'PBKDF2-HMAC-SHA256';
const ERWARTETER_CIPHER = 'AES-256-GCM';
const NONCE_LAENGE = 12;
// Nach oben offen waere die Rundenzahl ein Knopf zum Aufhaengen des Tabs.
const HOECHST_ITERATIONEN = 10_000_000;

const KOPF_PFAD = '/data/manifest.head.json';
const MANIFEST_PFAD = 'data/manifest.json';

const LABEL_INHALT = 'ata-export-enc-v1';
const LABEL_NAMEN = 'ata-export-name-v1';

export class DatenbaumFehler extends Error {
  constructor(nachricht: string) {
    super(nachricht);
    this.name = 'DatenbaumFehler';
  }
}

export function datenmodus(): Datenmodus {
  const gesetzt = process.env.NEXT_PUBLIC_DATENMODUS;
  if (gesetzt === undefined || gesetzt === '') {
    return 'api';
  }
  if (gesetzt === 'api' || gesetzt === 'statisch' || gesetzt === 'verschluesselt') {
    return gesetzt;
  }
  // Ausdruecklich werfen statt auf 'api' zurueckzufallen: Ein Tippfehler in
  // der Bauvariablen ergaebe sonst einen statischen Export, der beim
  // Anbieter vergeblich eine API sucht -- und der Fehler faende erst dort
  // statt, wo niemand mehr eine Meldung sieht.
  throw new DatenbaumFehler(
    `Unbekannter Datenmodus '${gesetzt}'. Erlaubt: api, statisch, verschluesselt.`,
  );
}

export interface Manifest {
  format: number;
  export_id: string;
  exported_at: string;
  run_id: string | null;
  run_started_at: string | null;
  run_completed_at: string | null;
  run_status: string | null;
  application_version: string;
  report_schema_version: string;
  signal_rule_version: string;
  // Symbol -> Verzeichnisname. `BRK B` ist ein gueltiges Symbol und kein
  // gueltiger Pfadbestandteil; die Zuordnung kommt aus dem Export, damit die
  // Oberflaeche die Regel nicht ein zweites Mal umsetzt.
  symbols: Record<string, string>;
  counts: Record<string, number>;
  stocks_without_chart: string[];
  // Pfad -> SHA-256 des Klartexts. Geprueft wird nach dem Entschluesseln:
  // Eine untergeschobene aeltere Fassung einer Datei entschluesselt sich
  // einwandfrei -- sie gehoert ja zu diesem Baum -- und faellt erst hier auf.
  files: Record<string, string>;
}

interface Klartextkopf {
  format: number;
  kdf: string;
  iterations: number;
  salt: string;
  cipher: string;
  tree_id: string;
  manifest: string;
}

export interface Schluessel {
  inhalt: CryptoKey;
  namen: CryptoKey;
  baumId: string;
  format: number;
}

export class Datenbaum {
  constructor(
    readonly manifest: Manifest,
    private readonly schluessel: Schluessel | null,
  ) {}

  /**
   * Eine Datei des Baums, entschluesselt und gegen das Manifest geprueft.
   *
   * Je Stand und Pfad nur einmal: Der Baum ist unveraenderlich, solange er
   * offen ist -- ein neuer Stand ist ein neuer Baum --, und `/data/*` kommt
   * mit `no-store` (public/_headers), der Browser haelt also nichts vor.
   * Ohne diesen Speicher entschluesselte jede Ansicht dieselbe Datei erneut.
   * Gehalten wird das geprueftte Ergebnis, nicht das Chiffrat; ein Fehler
   * bleibt nicht haengen, damit ein zweiter Versuch moeglich ist.
   */
  lade<T>(pfad: string): Promise<T> {
    const gemerkt = this.geladen.get(pfad);
    if (gemerkt !== undefined) {
      return gemerkt as Promise<T>;
    }
    const laden = this.ladeUngepuffert<T>(pfad).catch((ursache: unknown) => {
      this.geladen.delete(pfad);
      throw ursache;
    });
    this.geladen.set(pfad, laden);
    return laden;
  }

  private readonly geladen = new Map<string, Promise<unknown>>();

  private async ladeUngepuffert<T>(pfad: string): Promise<T> {
    const roh = await hole(await this.adresse(pfad), pfad);
    const klartext =
      this.schluessel === null ? roh : await entschluessele(this.schluessel, pfad, roh);
    await pruefeHash(this.manifest, pfad, klartext);
    return JSON.parse(new TextDecoder().decode(klartext)) as T;
  }

  /** Der Verzeichnisname einer Aktie -- `BRK B` wird zu `BRK-B`. */
  verzeichnis(symbol: string): string {
    const name = this.manifest.symbols[symbol.trim().toUpperCase()];
    if (name === undefined) {
      throw new DatenbaumFehler(`Die Aktie '${symbol}' steht nicht in diesem Stand.`);
    }
    return name;
  }

  private async adresse(pfad: string): Promise<string> {
    if (this.schluessel === null) {
      return `/${pfad}`;
    }
    return `/data/${await opakerName(this.schluessel.namen, pfad)}`;
  }
}

async function hole(adresse: string, pfad: string): Promise<Uint8Array> {
  const antwort = await fetch(adresse);
  if (!antwort.ok) {
    // Wie in `api.ts`: werfen statt einen Ersatzwert liefern. Eine
    // Oberflaeche, die eine fehlende Datei als leere Liste zeigt, behauptet,
    // es gebe nichts.
    throw new DatenbaumFehler(`${pfad} fehlt im Stand (HTTP ${String(antwort.status)}).`);
  }
  return new Uint8Array(await antwort.arrayBuffer());
}

async function pruefeHash(manifest: Manifest, pfad: string, klartext: Uint8Array): Promise<void> {
  const erwartet = manifest.files[pfad];
  if (erwartet === undefined) {
    throw new DatenbaumFehler(`${pfad} gehoert nicht zu diesem Stand.`);
  }
  const gemessen = alsHex(await crypto.subtle.digest('SHA-256', alsPuffer(klartext)));
  if (gemessen !== erwartet) {
    throw new DatenbaumFehler(
      `${pfad} stammt nicht aus diesem Stand -- die Pruefsumme weicht ab.`,
    );
  }
}

// --- Stufe 2: Schluessel, Namen, Entschluesselung -------------------------

export async function leiteSchluesselAb(
  passphrase: string,
  salt: Uint8Array,
  iterationen: number,
  baumId: string,
  format: number,
): Promise<Schluessel> {
  const material = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(passphrase),
    'PBKDF2',
    false,
    ['deriveBits'],
  );
  // Nur **eine** teure Ableitung; die Trennung in zwei Schluessel leistet das
  // HMAC danach. Derselbe Aufbau wie auf der Serverseite -- die feste
  // Vertragsdatei in `__fixtures__` haelt beide zusammen.
  const stamm = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt: alsPuffer(salt), iterations: iterationen, hash: 'SHA-256' },
    material,
    256,
  );
  const stammSchluessel = await crypto.subtle.importKey(
    'raw',
    stamm,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const inhaltRoh = await crypto.subtle.sign(
    'HMAC',
    stammSchluessel,
    new TextEncoder().encode(LABEL_INHALT),
  );
  const namenRoh = await crypto.subtle.sign(
    'HMAC',
    stammSchluessel,
    new TextEncoder().encode(LABEL_NAMEN),
  );
  return {
    inhalt: await crypto.subtle.importKey('raw', inhaltRoh, 'AES-GCM', false, ['decrypt']),
    namen: await crypto.subtle.importKey(
      'raw',
      namenRoh,
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['sign'],
    ),
    baumId,
    format,
  };
}

export async function opakerName(namenSchluessel: CryptoKey, pfad: string): Promise<string> {
  const roh = await crypto.subtle.sign('HMAC', namenSchluessel, new TextEncoder().encode(pfad));
  return alsHex(roh).slice(0, 32);
}

export async function entschluessele(
  schluessel: Schluessel,
  pfad: string,
  chiffrat: Uint8Array,
): Promise<Uint8Array> {
  const nonce = chiffrat.subarray(0, NONCE_LAENGE);
  const rest = chiffrat.subarray(NONCE_LAENGE);
  const zusatzdaten = new TextEncoder().encode(
    `${String(schluessel.format)}\n${schluessel.baumId}\n${pfad}`,
  );
  let gefuellt: ArrayBuffer;
  try {
    gefuellt = await crypto.subtle.decrypt(
      {
        name: 'AES-GCM',
        iv: alsPuffer(nonce),
        additionalData: alsPuffer(zusatzdaten),
        tagLength: 128,
      },
      schluessel.inhalt,
      alsPuffer(rest),
    );
  } catch {
    // Die Bibliothek unterscheidet nicht, warum: falsche Passphrase,
    // veraenderte Datei, vertauschter Pfad, fremder Baum. Genau das ist die
    // Zusage von GCM -- und die Meldung nennt deshalb alle vier Faelle,
    // statt einen davon zu behaupten.
    throw new DatenbaumFehler(
      `${pfad} liess sich nicht entschluesseln. Entweder ist die Passphrase falsch, ` +
        'oder die Datei gehoert nicht zu diesem Stand.',
    );
  }
  return entpacke(new Uint8Array(gefuellt));
}

async function entpacke(gefuellt: Uint8Array): Promise<Uint8Array> {
  // Vier Byte Laenge, dann gzip, dann Nullbytes bis zur Groessenklasse. Ohne
  // die Laenge waere die Auffuellung nicht vom Inhalt zu unterscheiden.
  const kopf = new DataView(gefuellt.buffer, gefuellt.byteOffset, 4);
  const laenge = kopf.getUint32(0, false);
  const gepackt = gefuellt.subarray(4, 4 + laenge);
  try {
    const strom = new Blob([alsPuffer(gepackt)])
      .stream()
      .pipeThrough(new DecompressionStream('gzip'));
    return new Uint8Array(await new Response(strom).arrayBuffer());
  } catch {
    // Nur nach bestandener Authentifizierung erreichbar -- also kein
    // Angriff, sondern eine auf dem Server kaputt geschriebene Datei. Auch
    // die soll als Meldung dieser Oberflaeche ankommen und nicht als
    // Rohfehler der Laufzeitumgebung.
    throw new DatenbaumFehler('Eine Datei des Stands ist beschaedigt.');
  }
}

// --- Oeffnen ---------------------------------------------------------------

/**
 * Oeffnet den Datenbaum: Manifest laden, in Stufe 2 vorher entschluesseln.
 *
 * Die Passphrase wird nur in Stufe 2 gebraucht und nirgends abgelegt -- nicht
 * im `localStorage`, nicht in einem Cookie. Sie steht im Passwortmanager des
 * Inhabers; ein neuer Tab fragt erneut.
 */
export async function oeffneDatenbaum(passphrase?: string): Promise<Datenbaum> {
  const modus = datenmodus();
  if (modus === 'api') {
    throw new DatenbaumFehler('Im API-Modus gibt es keinen Datenbaum.');
  }
  if (modus === 'statisch') {
    const roh = await hole(`/${MANIFEST_PFAD}`, MANIFEST_PFAD);
    return new Datenbaum(JSON.parse(new TextDecoder().decode(roh)) as Manifest, null);
  }

  if (passphrase === undefined || passphrase === '') {
    throw new DatenbaumFehler('Ohne Passphrase laesst sich dieser Stand nicht oeffnen.');
  }
  const kopf = pruefeKopf(await ladeKopf());
  const schluessel = await leiteSchluesselAb(
    passphrase,
    ausHex(kopf.salt),
    kopf.iterations,
    kopf.tree_id,
    kopf.format,
  );
  const roh = await hole(`/data/${kopf.manifest}`, MANIFEST_PFAD);
  const klartext = await entschluessele(schluessel, MANIFEST_PFAD, roh);
  // Das Manifest prueft sich nicht gegen sich selbst: Dass es echt ist, sagt
  // bereits die Entschluesselung -- wer es faelscht, muesste den Schluessel
  // haben.
  const manifest = JSON.parse(new TextDecoder().decode(klartext)) as Manifest;
  return new Datenbaum(manifest, schluessel);
}

async function ladeKopf(): Promise<unknown> {
  const antwort = await fetch(KOPF_PFAD);
  if (!antwort.ok) {
    throw new DatenbaumFehler(
      `Kein Stand gefunden (${KOPF_PFAD} antwortete mit ${String(antwort.status)}).`,
    );
  }
  return await antwort.json();
}

export function pruefeKopf(roh: unknown): Klartextkopf {
  // Der Kopf liegt im Klartext beim Anbieter und ist damit das Einzige, was
  // ein Angreifer mit Schreibzugriff frei waehlen kann. Er wird deshalb
  // **geprueft und nicht befolgt**: Ein herabgesetzter Rundenwert oder ein
  // ausgetauschtes Verfahren gilt hier als Fehler, nicht als Einstellung
  // (ADR 0060, Punkt 6).
  //
  // Wogegen das wirkt, ist genau zu benennen -- sonst verdraengt eine zu
  // gross erzaehlte Begruendung spaeter die echte. **Nicht** gegen einen
  // Angreifer, der den Kopf umschreibt: Der Arbeitsfaktor des gespeicherten
  // Chiffrats steht fest, sobald der Server verschluesselt hat; wer nur den
  // Kopf aendert, erreicht eine falsche Ableitung und damit einen Ausfall,
  // keinen Angriff auf die Passphrase. Wohl aber gegen einen **Server**, der
  // zu schwach verschluesselt hat -- eine falsch gesetzte Konfiguration, eine
  // aeltere Fassung des Exporters. Diese Pruefung ist die zweite Instanz
  // hinter der des Servers, und sie steht auf der Seite, die der Server
  // nicht kontrolliert.
  if (typeof roh !== 'object' || roh === null) {
    // Ohne diese Zeile wirft der naechste Feldzugriff einen TypeError der
    // Laufzeitumgebung, und die Oberflaeche zeigte ihn im Wortlaut an.
    throw new DatenbaumFehler('Der Kopf des Stands ist kein Objekt.');
  }
  const kopf = roh as Partial<Klartextkopf>;
  if (kopf.format !== ERWARTETES_FORMAT) {
    throw new DatenbaumFehler(
      `Unbekanntes Format des Datenbaums: ${String(kopf.format)}. ` +
        'Diese Oberflaeche kennt nur Format ' +
        String(ERWARTETES_FORMAT) +
        '.',
    );
  }
  if (kopf.kdf !== ERWARTETE_KDF || kopf.cipher !== ERWARTETER_CIPHER) {
    throw new DatenbaumFehler(
      `Der Stand nennt ein anderes Verfahren (${String(kopf.kdf)} / ${String(kopf.cipher)}). ` +
        'Diese Oberflaeche entschluesselt ausschliesslich ' +
        `${ERWARTETE_KDF} mit ${ERWARTETER_CIPHER}.`,
    );
  }
  if (
    typeof kopf.iterations !== 'number' ||
    !Number.isInteger(kopf.iterations) ||
    kopf.iterations < MINDEST_ITERATIONEN
  ) {
    throw new DatenbaumFehler(
      `Zu wenige Ableitungsrunden: ${String(kopf.iterations)}. ` +
        `Verlangt sind mindestens ${String(MINDEST_ITERATIONEN)}.`,
    );
  }
  if (kopf.iterations > HOECHST_ITERATIONEN) {
    // Nach oben offen waere der Kopf ein Knopf, mit dem sich der Tab
    // aufhaengen laesst: PBKDF2 laeuft im Vordergrund, und 10^12 Runden
    // kehren nie zurueck.
    throw new DatenbaumFehler(
      `Unglaubwuerdig viele Ableitungsrunden: ${String(kopf.iterations)}.`,
    );
  }
  if (typeof kopf.salt !== 'string' || kopf.salt.length < 32 || !istHex(kopf.salt)) {
    // Der Hex-Test ist keine Formsache: `ausHex` machte aus 64 unzulaessigen
    // Zeichen stillschweigend 32 Nullbytes, und die Oberflaeche meldete
    // danach "Passphrase falsch" -- fuer einen Fehler, der ganz woanders lag.
    throw new DatenbaumFehler('Das Salt des Stands ist zu kurz, fehlt oder ist kein Hex.');
  }
  if (typeof kopf.tree_id !== 'string' || kopf.tree_id === '' || kopf.tree_id.includes('\n')) {
    // Der Zeilenumbruch trennt die Bestandteile der Zusatzdaten. Eine
    // Kennung, die selbst einen enthaelt, machte die Kodierung mehrdeutig.
    throw new DatenbaumFehler('Die Kennung des Datenbaums fehlt oder ist unzulaessig.');
  }
  if (typeof kopf.manifest !== 'string' || !istHex(kopf.manifest) || kopf.manifest.length !== 32) {
    throw new DatenbaumFehler('Der Stand nennt kein gueltiges Manifest.');
  }
  return kopf as Klartextkopf;
}

// --- Kleinkram -------------------------------------------------------------

function alsPuffer(bytes: Uint8Array): ArrayBuffer {
  // `subarray` teilt sich den Puffer mit dem Original; WebCrypto braucht
  // genau den Ausschnitt und nicht den ganzen.
  return bytes.slice().buffer;
}

export function alsHex(puffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(puffer))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

export function istHex(text: string): boolean {
  return text.length % 2 === 0 && /^[0-9a-fA-F]*$/.test(text);
}

export function ausHex(hex: string): Uint8Array {
  // Streng: `Number.parseInt('zz', 16)` ergibt `NaN`, und `NaN` in ein
  // `Uint8Array` geschrieben wird zu 0. Ohne diese Pruefung waeren 64
  // unzulaessige Zeichen ein gueltig aussehendes Salt aus Nullbytes.
  if (!istHex(hex)) {
    throw new DatenbaumFehler('Kein gueltiger Hex-Wert.');
  }
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}
