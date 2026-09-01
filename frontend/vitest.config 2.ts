import path from 'node:path';

import { defineConfig } from 'vitest/config';

// Vitest und nicht Playwright: Geprueft wird, was das Dashboard aus
// gegebenen Daten macht -- Beschriftung, Reihenfolge, fehlende Werte. Ein
// Browserlauf brauchte eine laufende API und eine gefuellte Datenbank und
// pruefte damit etwas anderes.
//
// Ohne React-Plugin: Es bringt Fast Refresh fuer den Entwicklungsserver mit,
// den ein Testlauf nicht kennt -- und seine Vite-Version beisst sich mit der,
// die Vitest mitbringt. Fuer die Umwandlung von JSX genuegt esbuild.
export default defineConfig({
  // `tsconfig.json` steht auf `jsx: preserve`, weil Next.js die Umwandlung
  // selbst uebernimmt. Im Testlauf gibt es kein Next -- ohne diese Zeile
  // uebersetzte esbuild JSX in Aufrufe eines `React`, das niemand importiert.
  esbuild: { jsx: 'automatic' },
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    globals: false,
  },
});
