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

    **Laeuft unter Windows PowerShell 5.1 und unter pwsh 7.** Das ist keine
    Nebensache: Die Aufgabenplanung ruft ``powershell.exe`` auf, also 5.1 --
    eine Pruefung, die nur unter pwsh 7 durchlaeuft, prueft die falsche
    Umgebung.

.EXAMPLE
    powershell.exe -NoProfile -File scripts\pruefe-sicherung.ps1

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
. (Join-Path $PSScriptRoot 'datenbank-zugang.ps1')

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

# --- Der Datenbankzugang --------------------------------------------------
# Reine Zeichenarbeit, und sie entscheidet, welche Datenbank gesichert wird.
# Am 2026-10-10 sicherte das Skript einen fest verdrahteten Namen, den es auf
# dem Server nicht gibt -- diese Funktion ist die Korrektur, und sie gehoert
# geprueft und nicht behauptet.
Write-Output "`nDatenbankzugang aus ATA_DATABASE_URL:"

$gemerkteUrl = $env:ATA_DATABASE_URL
$zugangsWurzel = Join-Path ([System.IO.Path]::GetTempPath()) "ata-zugang-$([guid]::NewGuid())"
New-Item -ItemType Directory -Force -Path $zugangsWurzel | Out-Null

try {
    $env:ATA_DATABASE_URL = 'postgresql+psycopg://ata:geheim@localhost:5432/ata'
    $z = Lies-DatenbankZugang -Wurzel $zugangsWurzel
    Pruefe "der Datenbankname kommt aus der URL" 'ata' $z.Datenbank
    Pruefe "die Rolle kommt aus der URL" 'ata' $z.Benutzer
    Pruefe "das Passwort kommt aus der URL" 'geheim' $z.Passwort
    Pruefe "der Rechner kommt aus der URL" 'localhost' $z.Rechner
    Pruefe "der Port kommt aus der URL" 5432 $z.Port

    # Das Treiberkuerzel ist eine SQLAlchemy-Eigenheit. Ohne es wegzuschneiden
    # bleibt UserInfo leer, und die Rolle waere still falsch.
    $env:ATA_DATABASE_URL = 'postgresql://ata:geheim@db.example:6543/anders'
    $z = Lies-DatenbankZugang -Wurzel $zugangsWurzel
    Pruefe "auch ohne Treiberkuerzel" 'anders' $z.Datenbank
    Pruefe "abweichender Port" 6543 $z.Port

    # Ein Passwort mit Sonderzeichen steht in der URL prozentkodiert.
    $env:ATA_DATABASE_URL = 'postgresql+psycopg://ata:a%40b%3Ac@localhost/ata'
    $z = Lies-DatenbankZugang -Wurzel $zugangsWurzel
    Pruefe "prozentkodiertes Passwort wird entschluesselt" 'a@b:c' $z.Passwort
    Pruefe "fehlender Port wird zu 5432" 5432 $z.Port

    # Die .env wird gelesen, wenn die Umgebung nichts sagt -- mit
    # Anfuehrungszeichen und einem Kommentar davor, wie es in .env-Dateien
    # ueblich ist.
    $env:ATA_DATABASE_URL = $null
    Set-Content -Path (Join-Path $zugangsWurzel '.env') -Encoding ASCII -Value @(
        '# Kommentar',
        'ATA_TELEGRAM_TOKEN=egal',
        'ATA_DATABASE_URL="postgresql+psycopg://ata:ausDerDatei@localhost:5432/ausDerDatei"'
    )
    $z = Lies-DatenbankZugang -Wurzel $zugangsWurzel
    Pruefe "die .env wird gelesen" 'ausDerDatei' $z.Datenbank
    Pruefe "Anfuehrungszeichen gehoeren nicht zum Wert" 'ausDerDatei' $z.Passwort

    # Und die Umgebung gewinnt gegen die Datei -- sie ist die spezifischere
    # Angabe, etwa in der Umgebung eines Dienstkontos.
    $env:ATA_DATABASE_URL = 'postgresql+psycopg://ata:x@localhost:5432/ausDerUmgebung'
    $z = Lies-DatenbankZugang -Wurzel $zugangsWurzel
    Pruefe "die Umgebung gewinnt gegen die .env" 'ausDerUmgebung' $z.Datenbank

    # Nichts gesetzt: Abbruch mit Begruendung. **Kein Ersatzwert** -- ein
    # geratener Datenbankname ist schlimmer als keiner.
    $env:ATA_DATABASE_URL = $null
    Remove-Item (Join-Path $zugangsWurzel '.env') -Force
    $geworfen = $false
    try { Lies-DatenbankZugang -Wurzel $zugangsWurzel | Out-Null } catch { $geworfen = $true }
    Pruefe "ohne ATA_DATABASE_URL wird abgebrochen" $true $geworfen
}
finally {
    $env:ATA_DATABASE_URL = $gemerkteUrl
    Remove-Item $zugangsWurzel -Recurse -Force -ErrorAction SilentlyContinue
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
foreach ($name in @('pg_dump.exe', 'pg_restore.exe', 'psql.exe')) {
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
    return Starte-Skript -Skript $skript -Weitere (
        @('-Ziel', $ablage, '-PgBin', $stubBin) + $Weitere) -Umgebung $Umgebung
}

function Starte-Skript {
    param([string]$Skript, [string[]]$Weitere, [hashtable]$Umgebung = @{})

    $gemerkt = @{}
    foreach ($name in $Umgebung.Keys) {
        $gemerkt[$name] = [Environment]::GetEnvironmentVariable($name)
        [Environment]::SetEnvironmentVariable($name, $Umgebung[$name])
    }
    try {
        # **``Start-Process`` und nicht ``& exe ... 2> datei``.** Der
        # Operatorweg geht durch die Stromverarbeitung von PowerShell, und
        # die verhaelt sich in zwei Punkten gegen uns:
        #
        # 1. Windows PowerShell 5.1 macht aus stderr eines nativen Befehls
        #    einen ``NativeCommandError`` -- bei ``$ErrorActionPreference =
        #    'Stop'`` einen abbrechenden. Hier ist stderr aber der
        #    Normalfall: Jede Leitplanke *soll* dorthin schreiben.
        # 2. Was ankommt, ist dann nicht der rohe Text, sondern der
        #    **gerenderte** Fehlerdatensatz -- mit Zeilenumbruechen bei rund
        #    120 Zeichen. Ein Suchtext, der auf so einen Umbruch faellt,
        #    wird nicht gefunden, und einer daneben zufaellig schon. Genau
        #    das ist am 2026-10-09 passiert.
        #
        # ``Start-Process -RedirectStandardError`` umgeht beides: Die
        # Umleitung geschieht auf Prozessebene, PowerShell sieht den Strom
        # nie. Der Rueckgabewert kommt aus ``ExitCode`` statt aus
        # ``$LASTEXITCODE``.
        $fehlerdatei = Join-Path $spielwiese "stderr-$([guid]::NewGuid()).txt"
        $ausgabedatei = Join-Path $spielwiese "stdout-$([guid]::NewGuid()).txt"

        # Jedes Argument in Anfuehrungszeichen: ``-ArgumentList`` baut eine
        # Kommandozeile, und ein Pfad mit Leerzeichen zerfiele darin.
        $argumente = @('-NoProfile', '-File', $Skript) + $Weitere |
            ForEach-Object { '"{0}"' -f $_ }

        $lauf = Start-Process -FilePath (Get-Process -Id $PID).Path `
            -ArgumentList $argumente -Wait -PassThru -NoNewWindow `
            -RedirectStandardError $fehlerdatei `
            -RedirectStandardOutput $ausgabedatei

        $text = if (Test-Path $fehlerdatei) { Get-Content $fehlerdatei -Raw } else { '' }
        Remove-Item $fehlerdatei, $ausgabedatei -Force -ErrorAction SilentlyContinue

        return [pscustomobject]@{
            Code = $lauf.ExitCode
            Text = [string]$text
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

# **Die Umgebung ist vollstaendig, ausser dem, was gerade geprueft wird.**
# ``sicherung.ps1`` liest den Zugang aus ATA_DATABASE_URL, bevor es die
# Auslagerung prueft -- ohne diese Zeile braechen alle Leitplanken schon
# dort ab, und zwar mit der falschen Meldung.
$PRUEFURL = 'postgresql+psycopg://ata:x@localhost:5432/ata'
$leer = @{
    AWS_ACCESS_KEY_ID     = $null
    AWS_SECRET_ACCESS_KEY = $null
    ATA_DATABASE_URL      = $PRUEFURL
}
$gesetzt = @{
    AWS_ACCESS_KEY_ID     = 'AKIAPRUEFUNG'
    AWS_SECRET_ACCESS_KEY = 'geheim'
    ATA_DATABASE_URL      = $PRUEFURL
}

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

    # Nicht die Auslagerung, aber dieselbe Art Fehlschlag: Am 2026-10-09 warf
    # die Zaehlprobe bei fehlender Ablage einen rohen DriveNotFoundException
    # und endete mit 1 statt mit 2. Die 1 geht in der Aufgabenplanung unter.
    Pruefe-Leitplanke "eine fehlende Ablage bricht die Zaehlprobe mit 2 ab" 'gibt es nicht' (
        Starte-Skript -Umgebung $gesetzt -Skript (
            Join-Path $PSScriptRoot 'sicherung-probe.ps1') -Weitere @(
            '-Quelle', (Join-Path $spielwiese 'gibtesnicht'), '-PgBin', $stubBin))

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
