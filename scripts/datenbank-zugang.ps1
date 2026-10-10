<#
.SYNOPSIS
    Liest Host, Port, Benutzer, Datenbank und Passwort aus `ATA_DATABASE_URL`.

.DESCRIPTION
    **Dieselbe Quelle wie die Anwendung** -- nicht eine zweite Festlegung
    daneben. `laufzeiten.py` und `betriebsbericht.py` machen es seit immer so;
    die PowerShell-Skripte hatten den Namen stattdessen fest verdrahtet, und
    am 2026-10-10 hat genau das zugeschlagen: `pg_dump` suchte eine Datenbank
    `ai_trading_analyst`, die es auf dem Server nicht gibt.

    Ein fest verdrahteter Name ist eine Behauptung ueber eine Umgebung, die
    das Skript nicht kennt. Der Zugang der Anwendung ist dagegen per
    Definition richtig: Laeuft der Tageslauf, stimmt er.

    Gelesen wird zuerst die Umgebungsvariable, dann die `.env` im
    Projektwurzelverzeichnis -- in dieser Reihenfolge, weil die Umgebung des
    Dienstkontos die spezifischere Angabe ist.

    **Das Passwort steht damit nirgends auf der Kommandozeile** und in keinem
    Task-Argument. Es wird an `pg_dump` und `psql` ueber `PGPASSWORD` in der
    Prozessumgebung uebergeben, nicht als Parameter.
#>

function Lies-DatenbankZugang {
    [CmdletBinding()]
    param(
        # Projektwurzel; ohne Angabe das Verzeichnis ueber diesem Skript.
        [string]$Wurzel = (Split-Path $PSScriptRoot -Parent)
    )

    $url = $env:ATA_DATABASE_URL
    $quelle = 'der Umgebungsvariable ATA_DATABASE_URL'

    if (-not $url) {
        $envDatei = Join-Path $Wurzel '.env'
        if (Test-Path -LiteralPath $envDatei) {
            foreach ($zeile in Get-Content -LiteralPath $envDatei) {
                $gekuerzt = $zeile.Trim()
                if (-not $gekuerzt -or $gekuerzt.StartsWith('#')) { continue }
                $teile = $gekuerzt.Split('=', 2)
                if ($teile.Count -lt 2) { continue }
                if ($teile[0].Trim() -ne 'ATA_DATABASE_URL') { continue }
                # Anfuehrungszeichen sind in .env-Dateien ueblich und gehoeren
                # nicht zum Wert.
                $url = $teile[1].Trim().Trim('"').Trim("'")
                $quelle = "'$envDatei'"
                break
            }
        }
    }

    if (-not $url) {
        throw (
            "ATA_DATABASE_URL ist weder in der Umgebung noch in '$Wurzel\.env' " +
            "gesetzt. Ohne sie ist nicht feststellbar, welche Datenbank " +
            "gesichert werden soll -- und ein geratener Name ist schlimmer " +
            "als keiner."
        )
    }

    # Das Treiberkuerzel ('+psycopg') ist eine SQLAlchemy-Eigenheit und
    # gehoert nicht in eine URI. Ohne diesen Schritt bleibt UserInfo leer.
    $bereinigt = $url -replace '^postgresql\+[a-z0-9]+://', 'postgresql://'

    try {
        $uri = [uri]$bereinigt
    }
    catch {
        throw "ATA_DATABASE_URL aus $quelle ist keine lesbare Adresse."
    }

    $benutzerinfo = $uri.UserInfo.Split(':', 2)
    $datenbank = $uri.AbsolutePath.TrimStart('/')

    if (-not $datenbank) {
        throw "ATA_DATABASE_URL aus $quelle nennt keine Datenbank."
    }

    return [pscustomobject]@{
        Rechner    = if ($uri.Host) { $uri.Host } else { 'localhost' }
        Port       = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }
        Benutzer   = [uri]::UnescapeDataString($benutzerinfo[0])
        Passwort   = if ($benutzerinfo.Count -gt 1) {
            [uri]::UnescapeDataString($benutzerinfo[1])
        }
        else { '' }
        Datenbank  = [uri]::UnescapeDataString($datenbank)
        Quelle     = $quelle
    }
}
