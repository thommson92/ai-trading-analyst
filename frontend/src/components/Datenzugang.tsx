"use client";

// Der Zugang zum Datenbaum ausserhalb des Servers (ADR 0060).
//
// Drei Faelle, und nur der dritte ist sichtbar:
//
// 1. Im eigenen Netz (`api`) liegt zwischen Oberflaeche und Daten nichts --
//    diese Komponente reicht ihre Kinder unveraendert durch.
// 2. In Stufe 1 (`statisch`) oeffnet sie den Baum beim Laden.
// 3. In Stufe 2 (`verschluesselt`) fragt sie nach der Passphrase. Sie wird
//    nirgends abgelegt: nicht im `localStorage`, nicht in einem Cookie, nicht
//    in der Adresszeile. Sie steht im Passwortmanager des Inhabers, und ein
//    neuer Tab fragt erneut.
//
// In beiden Exportfaellen steht der **Stand** in der Kopfzeile. Das ist keine
// Verzierung: Ein Dashboard, das gestrige Zahlen zeigt, ohne es zu sagen, ist
// gefaehrlicher als eines, das gar nichts zeigt -- der Server koennte seit
// Tagen stehen (Bedrohung T10).
//
// Der Rahmen (Seitenleiste, Kopfzeile) liegt in allen drei Faellen hier:
// Auch die Passphrase-Abfrage steht in ihm, damit die Seite beim Oeffnen
// nicht springt.

import {
  useEffect,
  useState,
  type ReactNode,
  type SyntheticEvent,
} from "react";

import { setzeDatenbaum } from "@/lib/api";
import { datenmodus, oeffneDatenbaum, type Datenbaum } from "@/lib/datenbaum";

import { Seitenrahmen } from "./rahmen/Seitenrahmen";

function alsFehlertext(ursache: unknown): string {
  return ursache instanceof Error ? ursache.message : String(ursache);
}

const HOECHSTSTAND = "ata-hoechster-stand";

/**
 * Merkt sich den juengsten je gesehenen Export und meldet einen Rueckschritt.
 *
 * Wogegen das steht: Wer beim Anbieter schreiben darf, kann einen
 * **vollstaendigen alten Stand** zurueckspielen -- Manifest und Dateien
 * zusammen. Der ist in sich stimmig, jede Pruefsumme passt, und die
 * Verschluesselung merkt nichts davon. Zu erkennen ist er nur daran, dass er
 * aelter ist als der zuletzt gesehene.
 *
 * **Was das nicht leistet:** Der Vermerk liegt im Browser. Ein anderes
 * Geraet, ein privates Fenster oder geloeschte Websitedaten fangen bei null
 * an, und wer den Vermerk loescht, sieht die Warnung nicht mehr. Das ist ein
 * Hinweis und kein Beweis -- der Beweis waere ein Anker, den der Anbieter
 * nicht schreiben kann, und den gibt es hier nicht.
 */
function pruefeRueckschritt(exportiertAm: string): string | null {
  let bekannt: string | null = null;
  try {
    bekannt = window.localStorage.getItem(HOECHSTSTAND);
    if (bekannt === null || exportiertAm > bekannt) {
      window.localStorage.setItem(HOECHSTSTAND, exportiertAm);
    }
  } catch {
    // Kein Speicher, kein Hinweis -- aber auch kein Grund, den Stand nicht
    // anzuzeigen. Ein privates Fenster ist keine Fehlkonfiguration.
    return null;
  }
  if (bekannt !== null && exportiertAm < bekannt) {
    return (
      `Dieser Stand ist aelter als der zuletzt gesehene (${bekannt}). ` +
      "Das kann an einem zurueckgespielten Deployment liegen -- oder daran, " +
      "dass der Server seither nichts Neues hochgeladen hat und jemand eine " +
      "aeltere Fassung wiederhergestellt hat. Nachsehen lohnt sich."
    );
  }
  return null;
}

export function Stand({ baum }: { baum: Datenbaum }): ReactNode {
  const manifest = baum.manifest;
  const lauf =
    manifest.run_completed_at ??
    manifest.run_started_at ??
    "noch kein abgeschlossener Lauf";
  const [rueckschritt] = useState(() =>
    pruefeRueckschritt(manifest.exported_at),
  );
  return (
    <>
      <p className="stand">
        Stand: Lauf vom <strong>{lauf}</strong>, exportiert{" "}
        {manifest.exported_at}
        {manifest.stocks_without_chart.length > 0
          ? ` -- ohne Chart: ${manifest.stocks_without_chart.join(", ")}`
          : ""}
      </p>
      {rueckschritt !== null ? (
        <p className="stand fehler">{rueckschritt}</p>
      ) : null}
    </>
  );
}

export function Datenzugang({ children }: { children: ReactNode }): ReactNode {
  const [modus] = useState(() => datenmodus());
  const [baum, setBaum] = useState<Datenbaum | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [oeffnet, setOeffnet] = useState(false);

  useEffect(() => {
    if (modus !== "statisch") {
      return;
    }
    let abgemeldet = false;
    oeffneDatenbaum()
      .then((geoeffnet) => {
        if (!abgemeldet) {
          setzeDatenbaum(geoeffnet);
          setBaum(geoeffnet);
        }
      })
      .catch((ursache: unknown) => {
        if (!abgemeldet) {
          setFehler(alsFehlertext(ursache));
        }
      });
    return () => {
      abgemeldet = true;
    };
  }, [modus]);

  if (modus === "api") {
    return <Seitenrahmen>{children}</Seitenrahmen>;
  }

  async function oeffnen(ereignis: SyntheticEvent): Promise<void> {
    ereignis.preventDefault();
    setOeffnet(true);
    setFehler(null);
    try {
      const geoeffnet = await oeffneDatenbaum(passphrase);
      setzeDatenbaum(geoeffnet);
      setBaum(geoeffnet);
      // Nicht im Zustand behalten: Gebraucht wird sie nach dem Oeffnen nicht
      // mehr -- die abgeleiteten Schluessel liegen im Datenbaum.
      setPassphrase("");
    } catch (ursache: unknown) {
      setFehler(alsFehlertext(ursache));
    } finally {
      setOeffnet(false);
    }
  }

  if (baum === null) {
    return (
      <Seitenrahmen>
        <main>
          <h1>AI Trading Analyst</h1>
          {modus === "verschluesselt" ? (
            <form
              className="zugang"
              onSubmit={(ereignis) => {
                void oeffnen(ereignis);
              }}
            >
              <label htmlFor="passphrase">Passphrase</label>
              <input
                id="passphrase"
                type="password"
                autoComplete="current-password"
                value={passphrase}
                onChange={(ereignis) => {
                  setPassphrase(ereignis.target.value);
                }}
              />
              <button type="submit" disabled={oeffnet || passphrase === ""}>
                {oeffnet ? "Oeffnet ..." : "Stand oeffnen"}
              </button>
              <p className="gedaempft">
                Die Daten liegen verschluesselt. Die Passphrase wird nur in
                diesem Tab verwendet und nirgends gespeichert.
              </p>
            </form>
          ) : (
            <p>Stand wird geladen ...</p>
          )}
          {fehler !== null ? <p className="fehler">{fehler}</p> : null}
        </main>
      </Seitenrahmen>
    );
  }

  return <Seitenrahmen stand={<Stand baum={baum} />}>{children}</Seitenrahmen>;
}
