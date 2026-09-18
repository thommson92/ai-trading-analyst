import type { ReactNode } from 'react';

import { Badge, type BadgeVariante } from '@/components/ui/Badge';
import type { Recommendation } from '@/lib/api';
import { formatEmpfehlung } from '@/lib/format';

// Die Farbe folgt der Stufe, die das Backend vergeben hat (ADR 0046) -- die
// Oberflaeche stuft nichts ein.
const VARIANTE: Record<Recommendation, BadgeVariante> = {
  STRONG_CANDIDATE: 'gewinn',
  CANDIDATE: 'akzent',
  WATCH: 'neutral',
  AVOID_FOR_NOW: 'verlust',
  INSUFFICIENT_DATA: 'neutral',
};

export function Empfehlungsbadge({ stufe }: { stufe: Recommendation | null }): ReactNode {
  return (
    <Badge variante={stufe === null ? 'neutral' : VARIANTE[stufe]}>{formatEmpfehlung(stufe)}</Badge>
  );
}
