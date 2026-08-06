import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
  title: 'AI Trading Analyst',
  description: 'Persoenliches Analyse-Dashboard fuer Long-Swing-Trades',
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>): ReactNode {
  return (
    <html lang="de">
      <body>{children}</body>
    </html>
  );
}
