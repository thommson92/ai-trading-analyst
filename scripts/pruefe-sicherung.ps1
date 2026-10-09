<#
.SYNOPSIS
    Prueft die Auslagerung aus `sicherung.ps1` -- die Zerlegung der S3-URI
    und die Leitplanken, die vor dem Dump greifen.

.DESCRIPTION
    Geprueft wird, was ohne AWS-Zugang und ohne Datenbank pruefbar ist. Das
    ist weniger als der ganze Ablauf, aber genau der Teil, der sonst erst
    nachts auf dem Server auffaellt.

    **Was hier nicht geprueft wird**, und wo es stattdessen geprueft wird:
    Verschluesselung, Upload und die Lesbarkeit der externen Kopie brauchen
    `age`, einen Zugang und einen echten Dump. Das ist die Abnahme auf dem
    Server und danach `sicherung-extern-probe.ps1` -- einmal je Pflegetermin
    (ADR 0070, letzter Abschnitt des Nachtrags).

    Die Leitplanken liegen **vor** dem Dump, und das ist der Punkt: Ein
    fehlender Schluessel soll auffallen, bevor eine halbe Gigabyte
    geschrieben wurde, nicht danach -- und nicht jeden Tag neu.

.EXAMPLE
    pwsh -NoProfile -File scripts\pruefe-sicherung.ps1
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

. (Join-Path $PSScriptRoot 's3-ziel.ps1')

Write-Output "Zerlegung der S3-URI:"

$fall = ConvertTo-S3Ziel -Uri 's3://ata-sicherung/' -Dateiname 'db-2026-10-09.dump.age'
Pruefe "Eimer ohne Praefix" 'ata-sicherung' $fall.Eimer
Pruefe "Schluessel ohne Praefix" 'db-2026-10-09.dump.age' $fall.Schluessel

$fall = ConvertTo-S3Ziel -Uri 's3://ata-sicherung' -Dateiname 'db.dump.age'
Pruefe "ohne abschliessenden Schraegstrich" 'db.dump.age' $fall.Schluessel

$fall = ConvertTo-S3Ziel -Uri 's3://ata-sicherung/postgres/taeglich/' -Dateiname 'db.dump.age'
Pruefe "mehrstufiges Praefix bleibt erhalten" 'postgres/taeglich/db.dump.age' $fall.Schluessel
Pruefe "der Eimer ist nur das erste Glied" 'ata-sicherung' $fall.Eimer

foreach ($schlecht in @('d:\backups', 's3://', 'ata-sicherung')) {
    $geworfen = $false
    try { ConvertTo-S3Ziel -Uri $schlecht -Dateiname 'x' | Out-Null } catch { $geworfen = $true }
    Pruefe "'$schlecht' wird abgewiesen" $true $geworfen
}

# --- Die Leitplanken ------------------------------------------------------
# Sie laufen in einem eigenen Prozess, weil der Rueckgabewert die Aussage ist
# und `exit` die aufrufende Sitzung beenden wuerde.
#
# **Geprueft wird der Text, nicht nur der Rueckgabewert.** Jede Leitplanke
# endet mit 2, und fuenf Faelle, die alle nur auf die 2 sehen, bestaetigen
# sich gegenseitig: Griffe versehentlich immer die erste, waeren alle fuenf
# gruen. Die Meldung sagt, welche es war.
Write-Output "`nLeitplanken vor dem Dump:"

$spielwiese = Join-Path ([System.IO.Path]::GetTempPath()) "ata-sicherungspruefung-$([guid]::NewGuid())"
$stubBin = Join-Path $spielwiese 'bin'
New-Item -ItemType Directory -Force -Path $stubBin | Out-Null

# Nur die Existenz wird geprueft, nicht die Ausfuehrbarkeit -- die Leitplanken
# greifen alle, bevor irgendetwas davon aufgerufen wird.
foreach ($name in @('pg_dump.exe', 'pg_restore.exe')) {
    New-Item -ItemType File -Force -Path (Join-Path $stubBin $name) | Out-Null
}
$ageStub = Join-Path $spielwiese 'age.cmd'
$awsStub = Join-Path $spielwiese 'aws.cmd'
Set-Content -Path $ageStub -Value '@echo off' -Encoding ASCII
Set-Content -Path $awsStub -Value '@echo off' -Encoding ASCII

$skript = Join-Path $PSScriptRoot 'sicherung.ps1'
$ablage = Join-Path $spielwiese 'ablage'

function Starte-Sicherung {
    param([string[]]$Weitere, [hashtable]$Umgebung = @{})

    $gemerkt = @{}
    foreach ($name in $Umgebung.Keys) {
        $gemerkt[$name] = [Environment]::GetEnvironmentVariable($name)
        [Environment]::SetEnvironmentVariable($name, $Umgebung[$name])
    }
    try {
        $argumente = @(
            '-NoProfile', '-File', $skript,
            '-Ziel', $ablage, '-PgBin', $stubBin
        ) + $Weitere
        $ausgabe = & (Get-Process -Id $PID).Path @argumente 2>&1
        return [pscustomobject]@{
            Code = $LASTEXITCODE
            Text = ($ausgabe | Out-String)
        }
    }
    finally {
        foreach ($name in $Umgebung.Keys) {
            [Environment]::SetEnvironmentVariable($name, $gemerkt[$name])
        }
    }
}

function Pruefe-Leitplanke($Bezeichnung, $Erkennung, $Ergebnis) {
    if ($Ergebnis.Code -ne 2) {
        Write-Output "  FEHLT $Bezeichnung"
        Write-Output "        erwarteter Rueckgabewert: 2, erhalten: '$($Ergebnis.Code)'"
        $script:Fehlschlaege++
        return
    }
    if ($Ergebnis.Text -notmatch $Erkennung) {
        Write-Output "  FEHLT $Bezeichnung"
        Write-Output "        die Meldung nennt nicht '$Erkennung':"
        Write-Output "        $($Ergebnis.Text.Trim())"
        $script:Fehlschlaege++
        return
    }
    Write-Output "  ok    $Bezeichnung"
}

$leer = @{ AWS_ACCESS_KEY_ID = $null; AWS_SECRET_ACCESS_KEY = $null }
$gesetzt = @{ AWS_ACCESS_KEY_ID = 'AKIAPRUEFUNG'; AWS_SECRET_ACCESS_KEY = 'geheim' }

try {
    Pruefe-Leitplanke "-ExternesZiel ohne -AgeEmpfaenger bricht ab" '-AgeEmpfaenger' (
        Starte-Sicherung -Weitere @('-ExternesZiel', 's3://ata-sicherung/') -Umgebung $gesetzt)

    # Der wichtigste Fall: Ein privater Schluessel an dieser Stelle hiesse,
    # dass er auf dem Server liegt -- genau der Zustand, gegen den Punkt 3
    # des ADR 0070 gebaut ist.
    Pruefe-Leitplanke "ein privater age-Schluessel wird abgewiesen" 'oeffentlichen Schluessel' (
        Starte-Sicherung -Umgebung $gesetzt -Weitere @(
            '-ExternesZiel', 's3://ata-sicherung/',
            '-AgeEmpfaenger', 'AGE-SECRET-KEY-1QQQQQ'))

    Pruefe-Leitplanke "ein Dateipfad als -ExternesZiel wird abgewiesen" 'S3-URI' (
        Starte-Sicherung -Umgebung $gesetzt -Weitere @(
            '-ExternesZiel', 'd:\backups', '-AgeEmpfaenger', 'age1pruefung'))

    Pruefe-Leitplanke "ein nicht gefundenes age bricht ab" 'gibtesnicht' (
        Starte-Sicherung -Umgebung $gesetzt -Weitere @(
            '-ExternesZiel', 's3://ata-sicherung/',
            '-AgeEmpfaenger', 'age1pruefung',
            '-AgePfad', (Join-Path $spielwiese 'gibtesnicht.cmd'),
            '-AwsPfad', $awsStub))

    Pruefe-Leitplanke "fehlende AWS-Zugangsdaten brechen ab" 'AWS_ACCESS_KEY_ID' (
        Starte-Sicherung -Umgebung $leer -Weitere @(
            '-ExternesZiel', 's3://ata-sicherung/',
            '-AgeEmpfaenger', 'age1pruefung',
            '-AgePfad', $ageStub, '-AwsPfad', $awsStub))
}
finally {
    Remove-Item $spielwiese -Recurse -Force -ErrorAction SilentlyContinue
}

if ($script:Fehlschlaege -gt 0) {
    Write-Output "`n$script:Fehlschlaege Pruefung(en) fehlgeschlagen."
    exit 1
}
Write-Output "`nAlle Pruefungen bestanden."
exit 0
