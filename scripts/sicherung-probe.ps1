<#
.SYNOPSIS
    Zählprobe auf der jüngsten Sicherung (Audit-2-Maßnahme A2-M4).

.DESCRIPTION
    Stellt den jüngsten Dump in eine **Wegwerfdatenbank** wieder her, zählt
    die Zeilen der tragenden Tabellen und wirft die Wegwerfdatenbank wieder
    weg.

    Warum überhaupt: Ein Dump, den nie jemand zurückgespielt hat, ist eine
    Vermutung. Der Unterschied zwischen „die Datei ist da" und „die Daten
    sind da" fällt sonst genau dann auf, wenn man ihn nicht gebrauchen kann.

    **Die Produktivdatenbank wird nie angefasst.** Der Zielname ist fest
    verdrahtet und wird vorher geprüft; ein Wiederherstellen über den
    laufenden Bestand wäre der einzige Weg, mit einer Sicherung Schaden
    anzurichten.

    Ausgeführt bei der Einrichtung und danach bei jedem Pflegetermin
    (Doc 14, Abschnitt „Pflege").

.PARAMETER Quelle
    Verzeichnis mit den Dumps. Der jüngste wird genommen.

.PARAMETER Datei
    Statt des jüngsten ein bestimmter Dump.

.EXAMPLE
    powershell.exe -NoProfile -File C:\...\scripts\sicherung-probe.ps1 -Quelle D:\backups\ata
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Quelle,
    [string]$Datei,
    [string]$Benutzer = 'ata'
)

$ErrorActionPreference = 'Stop'

# Fest verdrahtet und nicht als Parameter: Ein Parameter liesse sich mit dem
# Produktivnamen belegen, und dieses Skript loescht seine Zieldatenbank am
# Ende.
$Probedatenbank = 'ata_restore_probe'
$Produktivdatenbank = 'ai_trading_analyst'

if ($Probedatenbank -eq $Produktivdatenbank) {
    Write-Error 'Die Probedatenbank darf nicht die Produktivdatenbank sein.'
    exit 2
}

$dump = if ($Datei) {
    Get-Item $Datei
}
else {
    Get-ChildItem (Join-Path $Quelle '*.dump') | Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

if (-not $dump) {
    Write-Error "In '$Quelle' liegt kein Dump. Lief die Sicherung schon einmal?"
    exit 2
}

Write-Output "Probe auf: $($dump.FullName) ($('{0:N1}' -f ($dump.Length / 1MB)) MB, $($dump.LastWriteTime))"

try {
    psql --username=$Benutzer --dbname=postgres `
        --command="DROP DATABASE IF EXISTS $Probedatenbank;" | Out-Null
    psql --username=$Benutzer --dbname=postgres `
        --command="CREATE DATABASE $Probedatenbank OWNER $Benutzer;" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Die Probedatenbank liess sich nicht anlegen." }

    pg_restore --username=$Benutzer --dbname=$Probedatenbank $dump.FullName
    # pg_restore meldet auch bei harmlosen Abweichungen einen Wert ungleich 0
    # (fehlende Rollen etwa). Deshalb entscheidet hier nicht der
    # Rueckgabewert, sondern ob die Zahlen darunter stimmen.
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "pg_restore meldete $LASTEXITCODE -- die Zaehlwerte unten entscheiden."
    }

    Write-Output ''
    Write-Output 'Zeilen in der wiederhergestellten Datenbank:'
    foreach ($tabelle in @('intraday_bars', 'analysis_runs', 'stock_reports', 'stocks')) {
        $anzahl = (psql --username=$Benutzer --dbname=$Probedatenbank --tuples-only `
                --no-align --command="SELECT count(*) FROM $tabelle;").Trim()
        Write-Output ("  {0,-16} {1}" -f $tabelle, $anzahl)
    }

    Write-Output ''
    Write-Output 'Zum Vergleich dieselben Zahlen aus der Produktivdatenbank:'
    foreach ($tabelle in @('intraday_bars', 'analysis_runs', 'stock_reports', 'stocks')) {
        $anzahl = (psql --username=$Benutzer --dbname=$Produktivdatenbank --tuples-only `
                --no-align --command="SELECT count(*) FROM $tabelle;").Trim()
        Write-Output ("  {0,-16} {1}" -f $tabelle, $anzahl)
    }

    Write-Output ''
    Write-Output 'Die Zahlen muessen zum Stand des Sicherungstages passen. Seither'
    Write-Output 'hinzugekommene Laeufe erklaeren eine Differenz -- eine Null nicht.'
}
finally {
    # Auch nach einem Abbruch: Eine liegen gebliebene Probedatenbank waere
    # beim naechsten Lauf im Weg und belegt Platz.
    psql --username=$Benutzer --dbname=postgres `
        --command="DROP DATABASE IF EXISTS $Probedatenbank;" | Out-Null
    Write-Output "Probedatenbank '$Probedatenbank' entfernt."
}
