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
        [string]$PgBin
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
    $kandidaten = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin' -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName "$Name.exe" } |
        Where-Object { Test-Path $_ } |
        Sort-Object { [int]($_ -replace '.*\\PostgreSQL\\(\d+)\\.*', '$1') } -Descending

    if ($kandidaten) { return $kandidaten[0] }

    throw (
        "'$Name' wurde weder im Suchpfad noch unter " +
        "'C:\Program Files\PostgreSQL\<Fassung>\bin' gefunden. Entweder die " +
        "PostgreSQL-Clientwerkzeuge installieren oder das bin-Verzeichnis " +
        "ueber -PgBin angeben."
    )
}
