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

.PARAMETER PgBin
    Verzeichnis mit `psql.exe` und `pg_restore.exe`. Nur nötig, wenn die
    PostgreSQL-Werkzeuge weder im Suchpfad noch unter
    `C:\Program Files\PostgreSQL\<Fassung>\bin` liegen.

.PARAMETER Benutzer
    Überschreibt die Rolle aus `ATA_DATABASE_URL`. Ohne Angabe gilt die URL
    — dieselbe Quelle wie für die Anwendung.

.PARAMETER VerwaltungsBenutzer
    Rolle für `CREATE DATABASE` und `DROP DATABASE`. Ohne Angabe dieselbe wie
    oben; die braucht dann das Recht `CREATEDB`:

        ALTER ROLE ata CREATEDB;

    Die Alternative ist `-VerwaltungsBenutzer postgres`, dann wird aber das
    Superuser-Passwort gebraucht. `CREATEDB` an die Anwendungsrolle zu geben
    ist das kleinere Übel: Es erlaubt das Anlegen neuer Datenbanken, nicht
    den Zugriff auf fremde.

.EXAMPLE
    powershell.exe -NoProfile -File C:\...\scripts\sicherung-probe.ps1 -Quelle C:\ata-backups
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Quelle,
    [string]$Datei,
    [string]$Benutzer,
    [string]$VerwaltungsBenutzer,
    [string]$PgBin
)

$ErrorActionPreference = 'Stop'

# Ein Dump unter 1 KiB kann keiner sein -- derselbe Wert wie in
# ``cli.py::MINDESTGROESSE_DUMP``, und aus demselben Grund: Ein gescheitertes
# ``pg_dump`` hinterlaesst eine leere Datei, und die bleibt absichtlich
# liegen (ADR 0071). Ohne diese Schranke probt dieses Skript die Ruine --
# am 2026-10-10 genau so geschehen, mit "0,0 MB" in der ersten Zeile.
$MindestgroesseDump = 1024
$script:Fehlgeschlagen = $false

. (Join-Path $PSScriptRoot 'postgres-werkzeuge.ps1')
. (Join-Path $PSScriptRoot 'datenbank-zugang.ps1')

function Abbruch($Text) {
    # **Nicht Write-Error.** Bei $ErrorActionPreference = 'Stop' ist das ein
    # abbrechender Fehler: Das Skript endet sofort mit Rueckgabewert 1, und
    # das 'exit 2' dahinter laeuft nie.
    [Console]::Error.WriteLine($Text)
    exit 2
}

try {
    $psql = Finde-PostgresWerkzeug -Name 'psql' -PgBin $PgBin
    $pgRestore = Finde-PostgresWerkzeug -Name 'pg_restore' -PgBin $PgBin
}
catch {
    Abbruch $_.Exception.Message
}

# **Die Ablage zuerst, mit eigener Meldung.** Fehlt sie, warf ``Join-Path``
# unten einen rohen ``DriveNotFoundException`` samt Aufrufstapel und endete
# mit Rueckgabewert 1 -- am 2026-10-09 auf dem Server genau so geschehen, weil
# die Doc-14-Beispiele ein Laufwerk 'D:' nannten, das es nicht gibt. Bei einem
# Skript, dessen Kern sein Rueckgabewert ist, ist das die stille Variante des
# Fehlschlags: Die 1 geht in der Menge gewoehnlicher Fehler unter.
if (-not $Datei -and -not (Test-Path -LiteralPath $Quelle)) {
    Abbruch (
        "Die Ablage '$Quelle' gibt es nicht. Stimmt der Pfad hinter -Quelle, " +
        "und ist das Laufwerk vorhanden? 'Get-PSDrive -PSProvider FileSystem' " +
        "zeigt, was es gibt."
    )
}

# **Der Zugang erst hinter der Ablage.** Beide Pruefungen melden einen Fehler
# der Umgebung, aber die Ablage ist der Gegenstand dieses Skripts: Wer
# ``-Quelle`` falsch angibt, soll das lesen und nicht etwas ueber
# ATA_DATABASE_URL.
try {
    $zugang = Lies-DatenbankZugang
}
catch {
    Abbruch $_.Exception.Message
}
if (-not $Benutzer) { $Benutzer = $zugang.Benutzer }
if (-not $VerwaltungsBenutzer) { $VerwaltungsBenutzer = $Benutzer }

# Der Zielname ist fest verdrahtet und nicht als Parameter: Ein Parameter
# liesse sich mit dem Produktivnamen belegen, und dieses Skript loescht seine
# Zieldatenbank am Ende.
#
# Der **Produktiv**name kommt dagegen aus ``ATA_DATABASE_URL`` -- fest
# verdrahtet war er eine Behauptung ueber eine Umgebung, die dieses Skript
# nicht kennt, und am 2026-10-10 war sie falsch.
$Probedatenbank = 'ata_restore_probe'
$Produktivdatenbank = $zugang.Datenbank

# Nur gesetzt, wenn die Rollen aus der URL kommen -- sonst gehoert das
# Passwort zu einem anderen Zugang. Dann gilt wieder die pgpass.conf.
if ($Benutzer -eq $zugang.Benutzer -and $zugang.Passwort) {
    $env:PGPASSWORD = $zugang.Passwort
}

function Rufe-Psql {
    param([string]$Als, [string]$Auf, [string]$Befehl, [switch]$Still)
    # **``& $psql`` und nicht ``psql``.** In den Zaehlschleifen stand bis zum
    # 2026-10-10 der blanke Name -- und laut Doc 14 liegt psql auf diesem
    # Server gerade *nicht* im Suchpfad. Die Werkzeugsuche oben waere damit
    # genau dort umgangen worden, wo es darauf ankommt.
    $argumente = @(
        '--no-password',
        "--host=$($zugang.Rechner)", "--port=$($zugang.Port)",
        "--username=$Als", "--dbname=$Auf", "--command=$Befehl"
    )
    if ($Still) { return (& $psql @argumente | Out-Null) }
    return (& $psql @argumente --tuples-only --no-align)
}

if ($Probedatenbank -eq $Produktivdatenbank) {
    Abbruch 'Die Probedatenbank darf nicht die Produktivdatenbank sein.'
}

$dump = if ($Datei) {
    Get-Item $Datei
}
else {
    Get-ChildItem (Join-Path $Quelle '*.dump') |
        Where-Object Length -ge $MindestgroesseDump |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

if (-not $dump) {
    $ruinen = @(Get-ChildItem (Join-Path $Quelle '*.dump') -ErrorAction SilentlyContinue)
    if ($ruinen.Count -gt 0) {
        Abbruch (
            "In '$Quelle' liegen $($ruinen.Count) Datei(en), aber keine ueber " +
            "$MindestgroesseDump Byte -- also keine brauchbare Sicherung. " +
            "Ein gescheitertes pg_dump hinterlaesst eine leere Datei; die " +
            "Meldung der Sicherung sagt, warum."
        )
    }
    Abbruch "In '$Quelle' liegt kein Dump. Lief die Sicherung schon einmal?"
}

Write-Output "Probe auf: $($dump.FullName) ($('{0:N1}' -f ($dump.Length / 1MB)) MB, $($dump.LastWriteTime))"

try {
    Rufe-Psql -Als $VerwaltungsBenutzer -Auf postgres -Still `
        -Befehl "DROP DATABASE IF EXISTS $Probedatenbank;"
    Rufe-Psql -Als $VerwaltungsBenutzer -Auf postgres -Still `
        -Befehl "CREATE DATABASE $Probedatenbank OWNER $Benutzer;"
    if ($LASTEXITCODE -ne 0) {
        throw (
            "Die Probedatenbank liess sich nicht anlegen. Bei 'keine " +
            "Berechtigung, um Datenbank zu erzeugen' fehlt der Rolle " +
            "'$VerwaltungsBenutzer' das Recht CREATEDB: " +
            "ALTER ROLE $VerwaltungsBenutzer CREATEDB; -- oder " +
            "-VerwaltungsBenutzer postgres verwenden."
        )
    }

    & $pgRestore --no-password `
        --host=$($zugang.Rechner) --port=$($zugang.Port) `
        --username=$Benutzer --dbname=$Probedatenbank $dump.FullName
    # pg_restore meldet auch bei harmlosen Abweichungen einen Wert ungleich 0
    # (fehlende Rollen etwa). Deshalb entscheidet hier nicht der
    # Rueckgabewert, sondern ob die Zahlen darunter stimmen.
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "pg_restore meldete $LASTEXITCODE -- die Zaehlwerte unten entscheiden."
    }

    Write-Output ''
    Write-Output 'Zeilen in der wiederhergestellten Datenbank:'
    foreach ($tabelle in @('intraday_bars', 'analysis_runs', 'stock_reports', 'stocks')) {
        $anzahl = (Rufe-Psql -Als $Benutzer -Auf $Probedatenbank `
                -Befehl "SELECT count(*) FROM $tabelle;" | Out-String).Trim()
        Write-Output ("  {0,-16} {1}" -f $tabelle, $anzahl)
    }

    Write-Output ''
    Write-Output "Zum Vergleich dieselben Zahlen aus '$Produktivdatenbank':"
    foreach ($tabelle in @('intraday_bars', 'analysis_runs', 'stock_reports', 'stocks')) {
        $anzahl = (Rufe-Psql -Als $Benutzer -Auf $Produktivdatenbank `
                -Befehl "SELECT count(*) FROM $tabelle;" | Out-String).Trim()
        Write-Output ("  {0,-16} {1}" -f $tabelle, $anzahl)
    }

    Write-Output ''
    Write-Output 'Die Zahlen muessen zum Stand des Sicherungstages passen. Seither'
    Write-Output 'hinzugekommene Laeufe erklaeren eine Differenz -- eine Null nicht.'
}
catch {
    # **Ohne diesen Zweig endet das Skript mit 1, nicht mit 2.** Ein ``throw``
    # unter ``$ErrorActionPreference = 'Stop'`` laeuft sonst bis nach draussen
    # und wird dort mit Aufrufstapel gerendert -- am 2026-10-10 genau so
    # geschehen. Die 1 geht in der Spalte "Letztes Ausfuehrungsergebnis"
    # unter; die 2 heisst hier wie im ganzen Projekt "Umgebung oder
    # Konfiguration".
    [Console]::Error.WriteLine("FEHLER: $($_.Exception.Message)")
    $script:Fehlgeschlagen = $true
}
finally {
    # Auch nach einem Abbruch: Eine liegen gebliebene Probedatenbank waere
    # beim naechsten Lauf im Weg und belegt Platz.
    Rufe-Psql -Als $VerwaltungsBenutzer -Auf postgres -Still `
        -Befehl "DROP DATABASE IF EXISTS $Probedatenbank;"
    Write-Output "Probedatenbank '$Probedatenbank' entfernt."
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

if ($script:Fehlgeschlagen) { exit 2 }
exit 0
