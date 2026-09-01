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
};

export default nextConfig;
