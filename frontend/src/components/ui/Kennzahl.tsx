import type { ReactNode } from 'react';

/**
 * Eine Zahl mit Beschriftung. Wer null uebergibt, bekommt einen Strich --
 * nie eine Null (ADR 0047).
 */
export function Kennzahl({
  label,
  wert,
  hinweis,
  betont = false,
}: {
  label: string;
  wert: ReactNode;
  hinweis?: ReactNode;
  betont?: boolean;
}): ReactNode {
  return (
    <div className={betont ? 'kennzahl kennzahl-betont' : 'kennzahl'}>
      <span className="kennzahl-label">{label}</span>
      <span className="kennzahl-wert">{wert ?? '–'}</span>
      {hinweis !== undefined && <span className="kennzahl-hinweis">{hinweis}</span>}
    </div>
  );
}

/** Mehrere Kennzahlen in einem Raster, das mit der Breite umbricht. */
export function Kennzahlen({ children }: { children: ReactNode }): ReactNode {
  return <div className="kennzahlen-raster">{children}</div>;
}
