<#
.SYNOPSIS
    Holt die neueste ausgelagerte Sicherung zurueck, entschluesselt sie und
    prueft, ob sie lesbar ist (ADR 0070, Nachtrag).

.DESCRIPTION
    Die taegliche Zaehlprobe (`sicherung-probe.ps1`) prueft die **lokale**
    Kopie. Ob die hochgeladene Datei wieder herunterkommt und sich
    entschluesseln laesst, prueft sie nicht -- und genau darauf kommt es an,
    wenn der Server verloren ist.

    **Dieses Skript laeuft nicht auf dem Server.** Es braucht zwei Dinge, die
    dort nichts zu suchen haben:

    - den **privaten** age-Schluessel. Laege er auf dem Server, koennte ein
      Angreifer die ausgelagerten Sicherungen lesen, und Punkt 3 des ADR 0070
      waere gegenstandslos;
    - einen AWS-Zugang mit **Leserecht**. Der Zugang des Servers hat nur
      `s3:PutObject` (Punkt 2) und kann diese Pruefung gar nicht ausfuehren.

    Es gehoert deshalb auf den Arbeitsrechner und in den Pflegetermin --
    einmal je Quartal, wie die uebrigen Punkte dort.

    Geprueft wird am Ende mit `pg_restore --list`: dasselbe Mittel und
    dieselbe Frage wie bei der lokalen Probe. Eine Datei, die herunterkommt
    und sich entschluesseln laesst, aber abgeschnitten ist, waere sonst
    unbemerkt.

.PARAMETER Quelle
    S3-URI, unter der die Sicherungen liegen -- dieselbe wie `-ExternesZiel`
    bei `sicherung.ps1`.

.PARAMETER SchluesselDatei
    Datei mit dem privaten age-Schluessel (`AGE-SECRET-KEY-1...`), aus dem
    Passwortmanager. Sie wird nur gelesen.

.PARAMETER Arbeitsverzeichnis
    Wohin heruntergeladen und entschluesselt wird. Wird am Ende geleert --
    ein entschluesselter Produktivdump soll nicht herumliegen.

.EXAMPLE
    pwsh -NoProfile -File scripts\sicherung-extern-probe.ps1 `
        -Quelle s3://ata-sicherung/ `
        -SchluesselDatei C:\Users\thomas\ata-age.key
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Quelle,
    [Parameter(Mandatory = $true)][string]$SchluesselDatei,
    [string]$Arbeitsverzeichnis,
    [string]$PgBin,
    [string]$AgePfad = 'age',
    [string]$AwsPfad = 'aws',
    [string]$EndpunktUrl
)

$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'postgres-werkzeuge.ps1')
. (Join-Path $PSScriptRoot 's3-ziel.ps1')

function Schreibe($Text) {
    Write-Output ("{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Text)
}

function Abbruch($Text) {
    [Console]::Error.WriteLine($Text)
    exit 2
}

if (-not (Test-Path $SchluesselDatei)) {
    Abbruch "Die Schluesseldatei '$SchluesselDatei' gibt es nicht."
}

try {
    $pgRestore = Finde-PostgresWerkzeug -Name 'pg_restore' -PgBin $PgBin
    foreach ($werkzeug in @($AgePfad, $AwsPfad)) {
        if (-not (Get-Command $werkzeug -ErrorAction SilentlyContinue)) {
            throw "'$werkzeug' wurde nicht gefunden."
        }
    }
    $ziel = ConvertTo-S3Ziel -Uri $Quelle -Dateiname 'platzhalter'
}
catch {
    Abbruch $_.Exception.Message
}

if (-not $Arbeitsverzeichnis) {
    $Arbeitsverzeichnis = Join-Path ([System.IO.Path]::GetTempPath()) "ata-externprobe-$([guid]::NewGuid())"
}
New-Item -ItemType Directory -Force -Path $Arbeitsverzeichnis | Out-Null

try {
    # Die Auflistung uebernimmt die Auswahl: Die Dateinamen tragen das Datum
    # im Format YYYY-MM-DD, und dessen Sortierung ist die zeitliche. Auf
    # `LastModified` zu gehen waere ungenauer -- ein spaeter von Hand
    # nachgeladener Stand saehe dann wie der neueste aus.
    $praefix = if ($ziel.Schluessel -eq 'platzhalter') { '' } else { $ziel.Schluessel -replace '/platzhalter$', '/' }
    $argumente = @('s3api', 'list-objects-v2', '--bucket', $ziel.Eimer, '--query', 'Contents[].Key', '--output', 'text')
    if ($praefix) { $argumente += @('--prefix', $praefix) }
    if ($EndpunktUrl) { $argumente += @('--endpoint-url', $EndpunktUrl) }

    Schreibe "Auflistung von 's3://$($ziel.Eimer)/$praefix'."
    $ausgabe = & $AwsPfad @argumente
    if ($LASTEXITCODE -ne 0) {
        throw "Die Auflistung endete mit Rueckgabewert $LASTEXITCODE. Traegt dieser Zugang Leserechte?"
    }

    $objekte = @(($ausgabe -split '\s+') | Where-Object { $_ -like '*.age' } | Sort-Object)
    if ($objekte.Count -eq 0) {
        throw "Unter 's3://$($ziel.Eimer)/$praefix' liegt keine verschluesselte Sicherung."
    }
    $neuestes = $objekte[-1]
    Schreibe "Neuestes Objekt: '$neuestes' (von $($objekte.Count))."

    $heruntergeladen = Join-Path $Arbeitsverzeichnis (Split-Path $neuestes -Leaf)
    $argumente = @('s3api', 'get-object', '--bucket', $ziel.Eimer, '--key', $neuestes, $heruntergeladen)
    if ($EndpunktUrl) { $argumente += @('--endpoint-url', $EndpunktUrl) }
    & $AwsPfad @argumente | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Der Download endete mit Rueckgabewert $LASTEXITCODE."
    }
    Schreibe ("Heruntergeladen, {0:N1} MB." -f ((Get-Item $heruntergeladen).Length / 1MB))

    $entschluesselt = Join-Path $Arbeitsverzeichnis 'entschluesselt.dump'
    & $AgePfad --decrypt --identity $SchluesselDatei --output $entschluesselt $heruntergeladen
    if ($LASTEXITCODE -ne 0) {
        throw "Die Entschluesselung endete mit Rueckgabewert $LASTEXITCODE. Passt der Schluessel zum Empfaenger?"
    }

    & $pgRestore --list $entschluesselt | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Die entschluesselte Datei ist kein lesbarer Dump (pg_restore --list, Rueckgabewert $LASTEXITCODE)."
    }
    Schreibe ("Probe bestanden: '$neuestes' kommt zurueck, laesst sich entschluesseln und ist lesbar.")
    exit 0
}
catch {
    [Console]::Error.WriteLine("FEHLER: $($_.Exception.Message)")
    exit 2
}
finally {
    # **Aufraeumen auch im Fehlerfall.** Was hier liegt, ist ein
    # entschluesselter Produktivbestand.
    Remove-Item $Arbeitsverzeichnis -Recurse -Force -ErrorAction SilentlyContinue
}
