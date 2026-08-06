// ESLint Flat Config.
//
// Architekturregel aus Doc 12: Keine Geschaeftslogik im Frontend. Das laesst
// sich nicht vollstaendig automatisch pruefen; die Regeln hier fangen die
// haeufigsten Wege ab, auf denen sich Logik einschleicht -- ungetypte Werte
// und stillschweigend ignorierte Fehler.

import js from '@eslint/js';
import nextPlugin from '@next/eslint-plugin-next';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: ['.next/**', 'node_modules/**', 'next-env.d.ts'],
  },
  js.configs.recommended,
  {
    plugins: { '@next/next': nextPlugin },
    rules: {
      ...nextPlugin.configs.recommended.rules,
      ...nextPlugin.configs['core-web-vitals'].rules,
    },
  },
  {
    // Typgestuetzte Regeln nur dort, wo der TypeScript-Compiler auch
    // Typinformationen liefert. Konfigurationsdateien gehoeren nicht zum
    // TS-Projekt und wuerden sonst einen Parsing-Fehler ausloesen.
    files: ['**/*.ts', '**/*.tsx'],
    extends: [...tseslint.configs.strictTypeChecked],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/explicit-function-return-type': [
        'error',
        { allowExpressions: true },
      ],
      '@typescript-eslint/consistent-type-imports': 'error',
      'no-console': ['warn', { allow: ['warn', 'error'] }],
    },
  },
);
