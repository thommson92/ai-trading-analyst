import type { ReactNode } from 'react';

export type BadgeVariante = 'neutral' | 'akzent' | 'gewinn' | 'verlust' | 'warnung' | 'info';

/** Ein kurzes Etikett. Die Variante ist eine Farbe, keine Bewertung. */
export function Badge({
  variante = 'neutral',
  title,
  children,
}: {
  variante?: BadgeVariante;
  title?: string;
  children: ReactNode;
}): ReactNode {
  return (
    <span className={`badge badge-${variante}`} title={title}>
      {children}
    </span>
  );
}
