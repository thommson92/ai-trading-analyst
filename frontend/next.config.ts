import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Statischer Export: Das Dashboard wird von derselben FastAPI-Anwendung
  // ausgeliefert, die die API bereitstellt -- ein Prozess, ein Port, kein
  // Node zur Laufzeit (ADR 0052).
  output: 'export',
  // Jede Route wird ein Verzeichnis mit `index.html`. Genau das findet ein
  // statischer Dateiserver ohne Sonderregeln; ohne die Angabe liefe `/lauf`
  // auf eine Datei, die er nicht sucht.
  trailingSlash: true,
  poweredByHeader: false,
  // Der Zero-Knowledge-Build landet in einem eigenen Verzeichnis: Next nimmt
  // bei `output: 'export'` das `distDir` als Exportziel. So ueberschreibt
  // `cli publish --full` nicht den LAN-Build in `out/` (ADR 0065). Das
  // Zwischenverzeichnis `.next` teilen sich beide -- nie parallel bauen.
  ...(process.env.NEXT_PUBLIC_DATENMODUS === 'verschluesselt' ? { distDir: 'out-verschluesselt' } : {}),
};

export default nextConfig;
