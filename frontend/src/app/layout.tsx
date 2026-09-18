import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Datenzugang } from "@/components/Datenzugang";

import "../styles/tokens.css";
import "./globals.css";
import "../styles/komponenten.css";

export const metadata: Metadata = {
  title: "AI Trading Analyst",
  description: "Persoenliches Analyse-Dashboard fuer Long-Swing-Trades",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>): ReactNode {
  return (
    <html lang="de">
      <body>
        {/* Ausserhalb des Servers liegt statt der API ein Datenbaum; er wird
            hier geoeffnet und der Stand in der Kopfzeile angezeigt (ADR 0060).
            Im eigenen Netz reicht die Komponente ihre Kinder in den Rahmen
            durch (ADR 0063). */}
        <Datenzugang>{children}</Datenzugang>
      </body>
    </html>
  );
}
