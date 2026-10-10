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

    **Zugang und Passwort kommen aus `ATA_DATABASE_URL`** — derselben Quelle,
    aus der auch die Anwendung sie nimmt (`datenbank-zugang.ps1`). Damit kann
    der Datenbankname nicht von der Anwendung abdriften; ein fest
    verdrahteter Name hat am 2026-10-10 genau das getan.

    Das Passwort steht **nicht** in den Task-Argumenten — die sind im
    Aufgabenplaner für jeden lesbar, der den Rechner sieht — sondern geht
    über `PGPASSWORD` in der Prozessumgebung an `pg_dump`. Eine
    `pgpass.conf` ist damit nicht mehr nötig; liegt eine, greift sie
    weiterhin, wenn die URL kein Passwort trägt.

    **Nie interaktiv.** Alle Aufrufe tragen `--no-password`: In der
    Aufgabenplanung gibt es keine Konsole, und eine Eingabeaufforderung
    hieße dort, dass der Vorgang bis zum Zeitlimit hängt statt mit einer
    Meldung zu scheitern.

.PARAMETER Ziel
    Verzeichnis für die Dumps. Wird angelegt, wenn es fehlt.

.PARAMETER Datenbank
.PARAMETER Benutzer
    Überschreiben, was in `ATA_DATABASE_URL` steht. Ohne Angabe gilt die
    URL — das ist der Normalfall. **Wird eines von beiden gesetzt, wird das
    Passwort aus der URL nicht verwendet**, weil es dann zu einem anderen
    Zugang gehören kann; dann braucht es eine `pgpass.conf`.

.PARAMETER PgBin
    Verzeichnis mit `pg_dump.exe` und `pg_restore.exe`. Nur nötig, wenn die
    PostgreSQL-Werkzeuge weder im Suchpfad noch unter
    `C:\Program Files\PostgreSQL\<Fassung>\bin` liegen.

.PARAMETER Aufbewahrungstage
    Wie lange Dumps **lokal** liegen bleiben. Vierzehn Tage: lang genug, um
    einen erst spät bemerkten Fehler zu überleben, kurz genug, dass der Ordner
    nicht wächst. Für die externe Kopie gilt diese Zahl nicht — dort entscheidet
    die Lebenszyklusregel am Bucket (ADR 0070, Punkt 4).

.PARAMETER ExternesZiel
    S3-URI für die Auslagerung, etwa `s3://ata-sicherung/`. Fehlt der
    Parameter, verhält sich das Skript unverändert — die Auslagerung ist ein
    zusätzliches Glied der Kette, kein neuer Zweck (ADR 0070, Punkt 5).

    Die Zugangsdaten stehen **nicht** hier, sondern in den Umgebungsvariablen
    `AWS_ACCESS_KEY_ID` und `AWS_SECRET_ACCESS_KEY` des Dienstkontos. Dasselbe
    Argument wie beim Datenbankpasswort: Task-Argumente kann jeder lesen, der
    den Rechner sieht.

.PARAMETER AgeEmpfaenger
    Der **öffentliche** age-Schlüssel (`age1…`), gegen den verschlüsselt wird.
    Pflicht, sobald `-ExternesZiel` gesetzt ist. Der private Schlüssel gehört
    in den Passwortmanager und nicht auf diesen Rechner (ADR 0070, Punkt 3) —
    ein Server, der entschlüsseln kann, hebt den Zweck der Auslagerung auf.

.PARAMETER EndpunktUrl
    Abweichender S3-Endpunkt, für einen anderen S3-kompatiblen Anbieter.
    Ohne Angabe gilt AWS S3 (ADR 0070, Nachtrag vom 2026-10-09).

.PARAMETER AgePfad
.PARAMETER AwsPfad
    Vollständige Pfade zu `age.exe` und `aws.exe`. Nur nötig, wenn sie nicht
    im Suchpfad liegen — nach dem Vorbild von `-PgBin`. Der Suchpfad eines
    Dienstkontos in der Aufgabenplanung ist nicht der der angemeldeten
    Sitzung, und das fällt erst nachts auf.

.EXAMPLE
    powershell.exe -NoProfile -File C:\...\scripts\sicherung.ps1 -Ziel C:\ata-backups

.EXAMPLE
    powershell.exe -NoProfile -File C:\...\scripts\sicherung.ps1 `
        -Ziel C:\ata-backups `
        -ExternesZiel s3://ata-sicherung/ `
        -AgeEmpfaenger age1qqqqq...
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Ziel,
    [string]$Datenbank,
    [string]$Benutzer,
    [string]$PgBin,
    [int]$Aufbewahrungstage = 14,
    [string]$ExternesZiel,
    [string]$AgeEmpfaenger,
    [string]$EndpunktUrl,
    [string]$AgePfad = 'age',
    [string]$AwsPfad = 'aws'
)

$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'postgres-werkzeuge.ps1')
. (Join-Path $PSScriptRoot 's3-ziel.ps1')
. (Join-Path $PSScriptRoot 'datenbank-zugang.ps1')

function Schreibe($Text) {
    $zeile = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Text
    Write-Output $zeile
    if ($script:Protokoll) { Add-Content -Path $script:Protokoll -Value $zeile }
}

function Abbruch($Text) {
    # **Nicht Write-Error.** Bei $ErrorActionPreference = 'Stop' ist das ein
    # abbrechender Fehler: Das Skript endet sofort mit Rueckgabewert 1, und
    # das 'exit 2' dahinter laeuft nie. Bei einem Skript, dessen Kern sein
    # Rueckgabewert ist, waere das die stille Variante des Fehlschlags.
    [Console]::Error.WriteLine($Text)
    exit 2
}

# **Vor dem Zielverzeichnis und vor dem Protokoll**: Fehlen die Werkzeuge,
# ist das kein Fehler dieser Sicherung, sondern der Umgebung. Er soll
# auffallen, bevor ein Protokoll beginnt, in dem dann nichts Brauchbares
# steht.
try {
    $pgDump = Finde-PostgresWerkzeug -Name 'pg_dump' -PgBin $PgBin
    $pgRestore = Finde-PostgresWerkzeug -Name 'pg_restore' -PgBin $PgBin
}
catch {
    Abbruch $_.Exception.Message
}

# **Der Zugang aus derselben Quelle wie die Anwendung.** Vor dem Dump, aus
# demselben Grund wie die Werkzeugsuche darueber: Eine fehlende
# ATA_DATABASE_URL ist ein Fehler der Umgebung und soll auffallen, bevor ein
# Protokoll beginnt, in dem dann nichts Brauchbares steht.
try {
    $zugang = Lies-DatenbankZugang
}
catch {
    Abbruch $_.Exception.Message
}

# Ein ausdruecklich genannter Benutzer oder Datenbankname kann zu einem
# anderen Zugang gehoeren als das Passwort in der URL. Dann bleibt das
# Passwort aussen vor, und es gilt wieder die pgpass.conf.
$ueberschrieben = [bool]$Datenbank -or [bool]$Benutzer
if (-not $Datenbank) { $Datenbank = $zugang.Datenbank }
if (-not $Benutzer) { $Benutzer = $zugang.Benutzer }

# **Auch die Auslagerung wird hier geprueft, nicht erst in ihrem Schritt.**
# Ein fehlender age-Empfaenger oder ein nicht gefundenes aws.exe sind Fehler
# der Umgebung. Sie erst nach dem Dump zu entdecken hiesse: vierzig Sekunden
# gearbeitet, eine halbe Gigabyte geschrieben, und dann am immer gleichen
# Punkt gescheitert -- jeden Tag neu.
$script:LaegertAus = [bool]$ExternesZiel
if ($script:LaegertAus) {
    if (-not $AgeEmpfaenger) {
        Abbruch (
            "-ExternesZiel ohne -AgeEmpfaenger: Unverschluesselt verlaesst " +
            "nichts diesen Rechner (ADR 0070, Punkt 3)."
        )
    }
    # Der oeffentliche age-Schluessel beginnt immer mit 'age1'. Ein privater
    # ('AGE-SECRET-KEY-1...') an dieser Stelle waere der Fehler, gegen den
    # Punkt 3 gebaut ist -- er lag dann auf dem Server.
    if ($AgeEmpfaenger -notlike 'age1*') {
        Abbruch (
            "-AgeEmpfaenger erwartet einen oeffentlichen Schluessel ('age1...'). " +
            "Der private Schluessel gehoert in den Passwortmanager und nicht " +
            "auf diesen Rechner."
        )
    }
    if ($ExternesZiel -notlike 's3://*') {
        Abbruch "-ExternesZiel erwartet eine S3-URI, etwa 's3://ata-sicherung/'."
    }
    foreach ($werkzeug in @($AgePfad, $AwsPfad)) {
        if (-not (Get-Command $werkzeug -ErrorAction SilentlyContinue)) {
            Abbruch (
                "'$werkzeug' wurde nicht gefunden. Entweder installieren oder " +
                "den vollen Pfad ueber -AgePfad bzw. -AwsPfad angeben -- der " +
                "Suchpfad eines Dienstkontos ist nicht der der Anmeldesitzung."
            )
        }
    }
    if (-not $env:AWS_ACCESS_KEY_ID -or -not $env:AWS_SECRET_ACCESS_KEY) {
        Abbruch (
            "AWS_ACCESS_KEY_ID und AWS_SECRET_ACCESS_KEY sind nicht gesetzt. " +
            "Sie gehoeren in die Umgebung des Dienstkontos, nicht in die " +
            "Task-Argumente."
        )
    }
}

try {
    if (-not (Test-Path $Ziel)) { New-Item -ItemType Directory -Force -Path $Ziel | Out-Null }
    $script:Protokoll = Join-Path $Ziel 'sicherung.log'

    $stempel = Get-Date -Format 'yyyy-MM-dd'
    $datei = Join-Path $Ziel "$Datenbank-$stempel.dump"

    Schreibe (
        "Sicherung von '$Datenbank' auf $($zugang.Rechner):$($zugang.Port) " +
        "als '$Benutzer' nach '$datei' beginnt. Zugang aus $($zugang.Quelle)."
    )

    # PGPASSWORD in der Prozessumgebung und nicht als Parameter: Eine
    # Kommandozeile ist auf dem Rechner lesbar, diese Variable nicht.
    if (-not $ueberschrieben -and $zugang.Passwort) {
        $env:PGPASSWORD = $zugang.Passwort
    }
    try {
        & $pgDump --format=custom --no-password `
            --host=$($zugang.Rechner) --port=$($zugang.Port) `
            --username=$Benutzer --dbname=$Datenbank --file=$datei
        $dumpWert = $LASTEXITCODE
    }
    finally {
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    }
    if ($dumpWert -ne 0) {
        throw (
            "pg_dump endete mit Rueckgabewert $dumpWert. Bei 'existiert nicht' " +
            "stimmt ATA_DATABASE_URL nicht zur Anlage; bei 'no password " +
            "supplied' traegt die URL kein Passwort und es gibt keine " +
            "pgpass.conf."
        )
    }

    # Eine vorhandene Datei ist noch keine brauchbare Sicherung: Ein
    # abgebrochener Schreibvorgang hinterlaesst ebenfalls eine. `--list`
    # liest das Inhaltsverzeichnis des Dumps und faellt ueber eine
    # abgeschnittene Datei -- billig und genau die Frage, auf die es ankommt.
    $groesse = (Get-Item $datei).Length
    if ($groesse -lt 1024) {
        throw "Die Sicherung ist nur $groesse Byte gross -- das kann kein vollstaendiger Dump sein."
    }
    & $pgRestore --list $datei | Out-Null
    if ($LASTEXITCODE -ne 0) {  # pg_restore --list liest nur die Datei
        throw "Die Sicherung ist nicht lesbar (pg_restore --list, Rueckgabewert $LASTEXITCODE)."
    }
    Schreibe ("Sicherung erfolgreich, {0:N1} MB." -f ($groesse / 1MB))

    # **Verschluesseln und hochladen -- nach der Lesbarkeitspruefung, vor dem
    # Aufraeumen.** Die Stelle ist nicht beliebig: Eine abgebrochene Datei
    # ausser Haus zu tragen waere schlimmer als keine, weil sie dort wie eine
    # Sicherung aussieht (ADR 0070, Punkt 5).
    if ($script:LaegertAus) {
        $verschluesselt = "$datei.age"

        Schreibe "Verschluesselung gegen '$AgeEmpfaenger' beginnt."
        & $AgePfad --recipient $AgeEmpfaenger --output $verschluesselt $datei
        if ($LASTEXITCODE -ne 0) {
            throw "age endete mit Rueckgabewert $LASTEXITCODE."
        }

        # Ein leeres Ergebnis waere der stille Fehlschlag: age hat etwas
        # geschrieben, der Rueckgabewert ist 0, und hochgeladen wuerde nichts.
        $verschluesselteGroesse = (Get-Item $verschluesselt).Length
        if ($verschluesselteGroesse -lt 1024) {
            throw "Die verschluesselte Datei ist nur $verschluesselteGroesse Byte gross."
        }

        # ``s3api put-object`` und nicht ``s3 cp``: **ein** PutObject, ohne
        # Transfermanager und ohne mehrteiligen Upload -- also genau die
        # Anfrage, die dieser Zugang tragen darf, und bei einem Fehlschlag
        # auch genau eine Ursache. (``s3 cp`` braeuchte entgegen einer
        # naheliegenden Annahme *keine* Leserechte; der Grund hier ist die
        # Eindeutigkeit, nicht das Recht.)
        #
        # Preis dieser Wahl: **5 GiB sind die Obergrenze** eines einzelnen
        # PutObject. Der Dump liegt bei einigen hundert Megabyte und waechst
        # mit jedem Handelstag; wird es eng, ist ``s3api create-multipart-upload``
        # der Weg und nicht ``s3 cp``.
        # **Nicht ``$ziel``.** PowerShell-Variablennamen sind unabhaengig von
        # der Gross-/Kleinschreibung: ``$ziel`` *ist* der Parameter ``$Ziel``,
        # und dessen ``[string]``-Typbindung ueberlebt jede Zuweisung. Das
        # Objekt wuerde also stillschweigend zu seiner Textform zerquetscht --
        # ``$ziel.Eimer`` waere leer, und das Aufraeumen weiter unten suchte
        # danach in einem Verzeichnis namens '@{Eimer=...; Schluessel=...}'.
        # Ohne Set-StrictMode meldet das nichts.
        $s3Ziel = ConvertTo-S3Ziel -Uri $ExternesZiel -Dateiname (Split-Path $verschluesselt -Leaf)

        $argumente = @(
            's3api', 'put-object',
            '--bucket', $s3Ziel.Eimer,
            '--key', $s3Ziel.Schluessel,
            '--body', $verschluesselt
        )
        if ($EndpunktUrl) { $argumente += @('--endpoint-url', $EndpunktUrl) }

        Schreibe ("Hochladen nach 's3://{0}/{1}' ({2:N1} MB)." -f $s3Ziel.Eimer, $s3Ziel.Schluessel, ($verschluesselteGroesse / 1MB))
        & $AwsPfad @argumente | Out-Null
        if ($LASTEXITCODE -ne 0) {
            # Die verschluesselte Datei bleibt absichtlich liegen: Sie laesst
            # sich von Hand hochladen, ohne den Dump erneut zu verschluesseln.
            # Die Aufbewahrungsfrist unten raeumt sie spaeter mit weg.
            throw (
                "Der Upload endete mit Rueckgabewert $LASTEXITCODE. " +
                "'$verschluesselt' liegt noch hier und kann von Hand hochgeladen werden."
            )
        }
        Schreibe "Auslagerung erfolgreich."
        Remove-Item $verschluesselt
    }

    # Erst jetzt: Waere dieser Block vor dem Dump gelaufen, haette ein
    # gescheiterter Lauf die letzten guten Staende geloescht.
    #
    # Das Muster fasst ``.dump`` und ``.dump.age`` zusammen -- liegengebliebene
    # verschluesselte Dateien eines gescheiterten Uploads sollen sich nicht
    # aufsummieren. **Nur lokal:** Extern loescht die Lebenszyklusregel am
    # Bucket, weil dieser Zugang kein Loeschrecht hat.
    $grenze = (Get-Date).AddDays(-$Aufbewahrungstage)
    $alte = Get-ChildItem (Join-Path $Ziel "$Datenbank-*.dump*") |
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
