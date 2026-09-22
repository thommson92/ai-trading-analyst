<#
.SYNOPSIS
    Findet pg_dump, pg_restore und psql -- auch ohne Suchpfad.

.DESCRIPTION
    Der PostgreSQL-Installer trägt sein `bin`-Verzeichnis **nicht**
    zwangsläufig in den PATH ein. Auf dem Server dieses Projekts tut er es
    nicht: Ein blankes `psql` endet dort mit „wurde nicht als Name eines
    Cmdlet ... erkannt".

    Für ein Skript, das die Aufgabenplanung startet, ist das der schlechteste
    Fehler: Er tritt erst auf, wenn niemand zusieht, und er sieht aus wie ein
    Tippfehler statt wie eine fehlende Installation.

    Die Reihenfolge ist Absicht. Ein ausdrücklich genannter Pfad gewinnt --
    wer mehrere Fassungen installiert hat, soll wählen können, ohne den PATH
    umzustellen. Danach der Suchpfad, denn wenn er stimmt, ist er die
    Wahrheit. Erst zuletzt die Standardinstallation, und dort die **neueste**
    Fassung: Ein Dump der älteren Fassung lässt sich von der neueren lesen,
    umgekehrt nicht.

    Dot-Source diese Datei, statt die zwanzig Zeilen zu kopieren:

        . (Join-Path $PSScriptRoot 'postgres-werkzeuge.ps1')
        $pgDump = Finde-PostgresWerkzeug -Name 'pg_dump' -PgBin $PgBin
        & $pgDump --version
#>

function Finde-PostgresWerkzeug {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$PgBin,
        # Nur fuer die Pruefung in der CI: Der Standardinstallationspfad laesst
        # sich auf einem Runner nicht nachstellen, ohne ihn anzulegen. Ein
        # Parameter mit dem echten Wert als Vorgabe haelt den produktiven
        # Aufruf unveraendert -- kein Anrufer setzt ihn.
        [string]$Wurzel = 'C:\Program Files\PostgreSQL'
    )

    if ($PgBin) {
        $pfad = Join-Path $PgBin "$Name.exe"
        if (Test-Path $pfad) { return $pfad }
        throw "In '$PgBin' liegt kein '$Name.exe'. Stimmt der Pfad hinter -PgBin?"
    }

    $imPfad = Get-Command $Name -ErrorAction SilentlyContinue
    if ($imPfad) { return $imPfad.Source }

    # Get-ChildItem statt eines festen Verzeichnisses: Die Fassungsnummer
    # steht im Pfad, und sie aendert sich mit jedem Hauptversionswechsel.
    #
    # **Das @() ist der Kern dieser Zeilen, kein Zierat.** Liefert die Suche
    # genau einen Treffer, gibt PowerShell ihn als blanke Zeichenkette zurueck
    # und nicht als einelementiges Feld -- `$kandidaten[0]` griffe dann nicht
    # das erste Element, sondern das erste *Zeichen*: das 'C' aus
    # 'C:\Program Files\...'. Der Aufrufer bekaeme einen Buchstaben statt eines
    # Pfades und scheiterte mit "Die Benennung C wurde nicht als Name eines
    # Cmdlet ... erkannt" -- am 2026-09-22 auf dem Server genau so geschehen.
    # Bei zwei installierten Fassungen faellt der Fehler nie auf.
    $kandidaten = @(
        Get-ChildItem (Join-Path $Wurzel "*\bin\$Name.exe") -ErrorAction SilentlyContinue |
            Sort-Object {
                # Die Fassung steht im Verzeichnis ueber 'bin' -- also am
                # Objekt selbst und nicht in einem Muster ueber den ganzen
                # Pfad. Ein Muster muesste die Wurzel kennen und braeche,
                # sobald sie anders heisst.
                $fassung = $_.Directory.Parent.Name
                if ($fassung -match '^(\d+)') { [int]$Matches[1] } else { 0 }
            } -Descending |
            ForEach-Object { $_.FullName }
    )

    if ($kandidaten.Count -gt 0) { return $kandidaten[0] }

    throw (
        "'$Name' wurde weder im Suchpfad noch unter " +
        "'$Wurzel\<Fassung>\bin' gefunden. Entweder die " +
        "PostgreSQL-Clientwerkzeuge installieren oder das bin-Verzeichnis " +
        "ueber -PgBin angeben."
    )
}
