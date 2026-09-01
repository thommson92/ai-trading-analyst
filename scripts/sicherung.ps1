<#
.SYNOPSIS
    Tägliche Sicherung der Produktivdatenbank (Audit-2-Maßnahme A2-M4).

.DESCRIPTION
    Ein `pg_dump` im Custom-Format, eine Prüfung, ob das Ergebnis lesbar ist,
    und das Wegräumen alter Stände.

    **Der Kern dieses Skripts ist sein Rückgabewert.** Eine Sicherung, die
    still scheitert, ist schlechter als keine: Sie erzeugt Vertrauen, das
    nicht gedeckt ist. Die Aufgabenplanung zeigt in der Spalte „Letztes
    Ausführungsergebnis" genau diesen Wert — er ist das einzige Signal, das
    ohne Zutun sichtbar wird.

    Ebenso wichtig ist die **Reihenfolge**: Erst wird gesichert und geprüft,
    dann werden alte Stände gelöscht. Umgekehrt räumte ein fehlgeschlagener
    Lauf die letzten funktionierenden Sicherungen weg.

    Das Passwort steht **nicht** hier und nicht in den Task-Argumenten,
    sondern in `%APPDATA%\postgresql\pgpass.conf` (eine Zeile:
    `localhost:5432:*:ata:<passwort>`). Task-Argumente sind im Aufgabenplaner
    für jeden lesbar, der den Rechner sieht.

.PARAMETER Ziel
    Verzeichnis für die Dumps. Wird angelegt, wenn es fehlt.

.PARAMETER Datenbank
    Name der zu sichernden Datenbank.

.PARAMETER Benutzer
    PostgreSQL-Rolle. Muss zur Zeile in der pgpass.conf passen.

.PARAMETER Aufbewahrungstage
    Wie lange Dumps liegen bleiben. Vierzehn Tage: lang genug, um einen erst
    spät bemerkten Fehler zu überleben, kurz genug, dass der Ordner nicht
    wächst.

.EXAMPLE
    powershell.exe -NoProfile -File C:\...\scripts\sicherung.ps1 -Ziel D:\backups\ata
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Ziel,
    [string]$Datenbank = 'ai_trading_analyst',
    [string]$Benutzer = 'ata',
    [int]$Aufbewahrungstage = 14
)

$ErrorActionPreference = 'Stop'

function Schreibe($Text) {
    $zeile = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Text
    Write-Output $zeile
    if ($script:Protokoll) { Add-Content -Path $script:Protokoll -Value $zeile }
}

try {
    if (-not (Test-Path $Ziel)) { New-Item -ItemType Directory -Force -Path $Ziel | Out-Null }
    $script:Protokoll = Join-Path $Ziel 'sicherung.log'

    $stempel = Get-Date -Format 'yyyy-MM-dd'
    $datei = Join-Path $Ziel "$Datenbank-$stempel.dump"

    Schreibe "Sicherung von '$Datenbank' nach '$datei' beginnt."
    pg_dump --format=custom --username=$Benutzer --dbname=$Datenbank --file=$datei
    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump endete mit Rueckgabewert $LASTEXITCODE."
    }

    # Eine vorhandene Datei ist noch keine brauchbare Sicherung: Ein
    # abgebrochener Schreibvorgang hinterlaesst ebenfalls eine. `--list`
    # liest das Inhaltsverzeichnis des Dumps und faellt ueber eine
    # abgeschnittene Datei -- billig und genau die Frage, auf die es ankommt.
    $groesse = (Get-Item $datei).Length
    if ($groesse -lt 1024) {
        throw "Die Sicherung ist nur $groesse Byte gross -- das kann kein vollstaendiger Dump sein."
    }
    pg_restore --list $datei | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Die Sicherung ist nicht lesbar (pg_restore --list, Rueckgabewert $LASTEXITCODE)."
    }
    Schreibe ("Sicherung erfolgreich, {0:N1} MB." -f ($groesse / 1MB))

    # Erst jetzt: Waere dieser Block vor dem Dump gelaufen, haette ein
    # gescheiterter Lauf die letzten guten Staende geloescht.
    $grenze = (Get-Date).AddDays(-$Aufbewahrungstage)
    $alte = Get-ChildItem (Join-Path $Ziel "$Datenbank-*.dump") |
        Where-Object LastWriteTime -lt $grenze
    foreach ($eintrag in $alte) {
        Remove-Item $eintrag.FullName
        Schreibe "Alten Stand entfernt: $($eintrag.Name)"
    }

    exit 0
}
catch {
    Schreibe "FEHLER: $($_.Exception.Message)"
    # Nicht 1: Der Aufgabenplaner zeigt den Wert hexadezimal, und eine 1
    # geht in der Menge gewoehnlicher Fehler unter. 2 heisst hier wie im
    # ganzen Projekt "Umgebung oder Konfiguration".
    exit 2
}
