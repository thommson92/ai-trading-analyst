# ADR 0015: Lock-Dateien plattformunabhängig erzeugen (uv statt pip-compile)

- Status: Angenommen
- Datum: 2026-08-12

## Kontext

[ADR 0008](0008-reproduzierbare-installation.md) legt fest, dass die
Installation ausschließlich über zwei eingecheckte Lock-Dateien mit
Hash-Verifikation läuft, erzeugt mit `pip-compile` aus `pip-tools`. Diese
Entscheidung bleibt richtig — der **Erzeuger** der Dateien hat aber eine
Eigenschaft, die erst mit der IBKR-Integration ([ADR 0014](0014-ibkr-produktivintegration-freigegeben.md))
schmerzhaft wurde.

Seitdem hat das Projekt zwei Zielplattformen:

- Entwicklung auf macOS, CI auf Ubuntu,
- **Betrieb auf Windows** — dort läuft die TWS, also muss das Backend dort
  laufen.

`pip-compile` löst die Abhängigkeiten für *die Plattform auf, auf der es
läuft*, und wertet dabei die Umgebungsmarker der Pakete aus, statt sie in die
Lock-Datei zu übernehmen. Eine auf macOS erzeugte Lock-Datei ist damit eine
macOS-Lock-Datei. Beide möglichen Fehlerrichtungen sind am 2026-08-12
tatsächlich eingetreten:

1. **Zu viel.** `uvicorn[standard]` verlangt `uvloop` mit dem Marker
   `sys_platform != 'win32'`. In der Lock-Datei stand `uvloop` ohne diesen
   Marker; unter Windows brach die Installation ab, weil es dafür keine
   Distribution gibt. Behoben durch Verzicht auf das Extra — das war die
   Behandlung des Symptoms.
2. **Zu wenig.** `click` verlangt `colorama` mit dem Marker
   `platform_system == "Windows"`. Auf macOS ist der Marker falsch, also fiel
   das Paket ganz aus der Lock-Datei. Unter Windows scheiterte die
   Installation daran mit `In --require-hashes mode, all requirements must
   have their versions pinned with ==`.

Die zweite Richtung lässt sich nicht durch Weglassen einer Abhängigkeit
umgehen: Das fehlende Paket ist eine transitive Anforderung, die auf der
Zielplattform gebraucht wird.

## Entscheidung

Die Lock-Dateien werden ab sofort **plattform- und versionsunabhängig**
erzeugt, mit `uv pip compile --universal`:

```bash
uv pip compile --universal --generate-hashes \
    --output-file requirements.lock.txt pyproject.toml
uv pip compile --universal --generate-hashes --extra dev \
    --output-file requirements-dev.lock.txt pyproject.toml
```

`--universal` schreibt die Umgebungsmarker in die Lock-Datei, statt sie
auszuwerten:

```text
colorama==0.4.6 ; sys_platform == 'win32'
psycopg-binary==3.3.4 ; implementation_name != 'pypy'
```

Damit entscheidet **`pip` auf dem Zielrechner**, welche Zeilen für ihn
gelten, und nicht der Rechner, auf dem die Datei erzeugt wurde.

**Unverändert bleibt alles aus ADR 0008**, was den eigentlichen Gegenstand
jener Entscheidung ausmacht: zwei eingecheckte Lock-Dateien, Installation
ausschließlich mit `pip install --require-hashes -r …` gefolgt von
`pip install --no-deps -e .`, Hash-Verifikation von Version *und* Artefakt.
Die erzeugten Dateien sind weiterhin gewöhnliche
`requirements.txt`-Dateien, die `pip` ohne Zusatzwerkzeug installiert.

`uv` ist damit — wie `pip-tools` zuvor — **ausschließlich ein Werkzeug zur
Wartung der Lock-Dateien**, keine Laufzeit-, Test- oder CI-Abhängigkeit. Die
CI installiert unverändert mit `pip`.

## Begründung

Die Alternativen wurden verworfen:

- **Je eine Lock-Datei pro Plattform** verdoppelt die Wartung, und beide
  Dateien können auseinanderlaufen, ohne dass es auffällt: Ein Entwickler auf
  macOS bemerkt einen Fehler in der Windows-Datei erst auf dem Server.
- **Die fehlenden Pakete von Hand in `pyproject.toml` aufnehmen** (also
  `colorama` als direkte Abhängigkeit führen) behandelt genau einen Fall.
  Beim nächsten plattformabhängigen transitiven Paket steht dasselbe Problem
  wieder da — und zwar erneut erst auf dem Zielsystem.
- **Marker von Hand in die erzeugte Datei nachtragen** überlebt die nächste
  Regenerierung nicht.
- **Bei `pip-compile` bleiben** ist keine Option: Es kennt keinen
  universellen Modus. Hinzu kommt der in ADR 0008 dokumentierte Umstand, dass
  `pip-compile` 7.6.0 mit aktuellem `pip` (26.x) gar nicht mehr läuft und
  schon bisher eine eigens auf eine ältere `pip`-Version festgelegte
  Hilfsumgebung brauchte. `uv` läuft als eigenständiges Programm ohne diese
  Kopplung.

Der eigentliche Gewinn ist aber nicht die Werkzeugwahl, sondern dass eine
ganze Fehlerklasse verschwindet: Fehler dieser Art zeigen sich
grundsätzlich nicht dort, wo sie entstehen (Entwicklungsrechner), sondern
erst auf dem Zielsystem — im vorliegenden Fall mitten in der Inbetriebnahme.

## Konsequenzen

- `pyproject.toml` führt das Extra `lock` nicht mehr auf `pip-tools`, sondern
  verweist auf `uv`; `uv` wird nicht als Python-Abhängigkeit installiert,
  sondern als Programm bereitgestellt (`pipx install uv`, `brew install uv`
  oder das Installationsskript des Projekts).
- Die Lock-Dateien enthalten jetzt Marker-Zeilen und decken alle von
  `requires-python` erlaubten Python-Versionen ab (3.12 und 3.13). Sie sind
  dadurch etwas länger als die bisherigen.
- Wer eine Abhängigkeit ändert, erzeugt beide Dateien neu und checkt sie ein.
  Das Ergebnis ist auf jedem Rechner identisch — vorher hing es davon ab, wer
  die Datei erzeugt hat.
- `uvicorn` bleibt ohne das Extra `standard`. Der Verzicht war zwar durch
  diese Entscheidung nicht mehr erzwungen, seine Bestandteile werden aber
  nicht gebraucht, und `uvloop` gibt es auf dem Zielsystem ohnehin nicht.
- ADR 0008 bleibt in Kraft; dieses ADR ersetzt dort ausschließlich die
  Festlegung auf `pip-compile` als Erzeuger.
