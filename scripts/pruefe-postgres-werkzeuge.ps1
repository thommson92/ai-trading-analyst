<#
.SYNOPSIS
    Prueft `postgres-werkzeuge.ps1` -- Syntax aller Skripte und die Auswahl
    der PostgreSQL-Werkzeuge.

.DESCRIPTION
    Am 2026-09-22 gab `Finde-PostgresWerkzeug` auf dem Server den Buchstaben
    `C` statt eines Pfades zurueck: Bei **genau einer** installierten Fassung
    ist das Suchergebnis eine blanke Zeichenkette, und `[0]` griff darauf das
    erste Zeichen. Der Fehler konnte nur dort auftreten -- auf einem
    Entwicklungsrechner mit zwei Fassungen, und auf macOS und Linux
    ueberhaupt nicht.

    Das ist dieselbe Art Fehler, fuer die es den Windows-Job in der CI schon
    gibt (uvloop, colorama -- ADR 0015): unsichtbar ueberall ausser dort, wo
    er zaehlt. Diese Pruefung schliesst die Luecke.

    **Ohne Pester.** Vier Faelle und ein Syntaxdurchlauf rechtfertigen keine
    zusaetzliche Abhaengigkeit; der Rueckgabewert traegt das Ergebnis.

.EXAMPLE
    pwsh -NoProfile -File scripts\pruefe-postgres-werkzeuge.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$script:Fehlschlaege = 0

function Pruefe($Bezeichnung, $Erwartet, $Erhalten) {
    if ($Erwartet -ceq $Erhalten) {
        Write-Output "  ok    $Bezeichnung"
    }
    else {
        Write-Output "  FEHLT $Bezeichnung"
        Write-Output "        erwartet: '$Erwartet'"
        Write-Output "        erhalten: '$Erhalten'"
        $script:Fehlschlaege++
    }
}

# --- Syntax aller Skripte -------------------------------------------------
# Ein Skript, das die Aufgabenplanung startet, darf nicht an einem Tippfehler
# scheitern, den niemand vor Mitternacht sieht.
Write-Output "Syntaxpruefung:"
foreach ($datei in Get-ChildItem $PSScriptRoot -Filter '*.ps1') {
    $fehler = $null
    $tokens = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $datei.FullName, [ref]$tokens, [ref]$fehler) | Out-Null
    if ($fehler.Count -gt 0) {
        Write-Output "  FEHLT $($datei.Name): $($fehler[0].Message)"
        $script:Fehlschlaege++
    }
    else {
        Write-Output "  ok    $($datei.Name)"
    }
}

. (Join-Path $PSScriptRoot 'postgres-werkzeuge.ps1')

# Ein Name, den es auf keinem Runner gibt: Der Suchpfad wird vor der
# Standardinstallation geprueft, und Windows-Runner bringen ein echtes psql
# mit. Mit 'psql' pruefte dieser Test den Suchpfad statt der Auswahl.
$werkzeug = 'pg_pruefling'
$wurzel = Join-Path ([System.IO.Path]::GetTempPath()) "ata-pgpruefung-$([guid]::NewGuid())"

function Lege-Fassung-An($Fassung) {
    $bin = Join-Path $wurzel (Join-Path $Fassung 'bin')
    New-Item -ItemType Directory -Force -Path $bin | Out-Null
    $exe = Join-Path $bin "$werkzeug.exe"
    New-Item -ItemType File -Force -Path $exe | Out-Null
    return $exe
}

try {
    Write-Output "`nAuswahl der Werkzeuge:"

    # 1. Der Regressionsfall. Genau eine Fassung -- frueher kam hier 'C'.
    $erwartet = Lege-Fassung-An '16'
    $erhalten = Finde-PostgresWerkzeug -Name $werkzeug -Wurzel $wurzel
    Pruefe "genau eine Fassung liefert den vollen Pfad" $erwartet $erhalten

    # 2. Zwei Fassungen: die neuere gewinnt. Ein Dump der aelteren Fassung
    #    laesst sich von der neueren lesen, umgekehrt nicht.
    $neuer = Lege-Fassung-An '17'
    $erhalten = Finde-PostgresWerkzeug -Name $werkzeug -Wurzel $wurzel
    Pruefe "zwei Fassungen liefern die neuere" $neuer $erhalten

    # 3. Nichts gefunden: Abbruch mit Begruendung, nicht stilles Nichts.
    $leer = Join-Path ([System.IO.Path]::GetTempPath()) "ata-pgleer-$([guid]::NewGuid())"
    New-Item -ItemType Directory -Force -Path $leer | Out-Null
    $geworfen = $false
    try { Finde-PostgresWerkzeug -Name $werkzeug -Wurzel $leer | Out-Null }
    catch { $geworfen = $true }
    Pruefe "ohne Treffer wird abgebrochen" $true $geworfen
    Remove-Item $leer -Recurse -Force -ErrorAction SilentlyContinue

    # 4. Ein ausdruecklich genannter Pfad gewinnt gegen die Suche.
    $ausdruecklich = Split-Path $erwartet -Parent
    $erhalten = Finde-PostgresWerkzeug -Name $werkzeug -PgBin $ausdruecklich -Wurzel $wurzel
    Pruefe "-PgBin gewinnt gegen die Suche" $erwartet $erhalten
}
finally {
    Remove-Item $wurzel -Recurse -Force -ErrorAction SilentlyContinue
}

if ($script:Fehlschlaege -gt 0) {
    Write-Output "`n$script:Fehlschlaege Pruefung(en) fehlgeschlagen."
    exit 1
}
Write-Output "`nAlle Pruefungen bestanden."
exit 0
