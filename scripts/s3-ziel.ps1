<#
.SYNOPSIS
    Zerlegt eine S3-URI in Eimer und Objektschluessel.

.DESCRIPTION
    Eine eigene Datei aus demselben Grund wie `postgres-werkzeuge.ps1`: Eine
    Funktion laesst sich pruefen, ein Skript nur ausfuehren. `sicherung.ps1`
    laedt sie und `pruefe-sicherung.ps1` ebenso.

    Der Objektschluessel ist das, was beim Anbieter spaeter in der Konsole
    steht. Faellt die Zerlegung falsch aus, landet die Sicherung unter einem
    unerwarteten Namen -- und das faellt genau dann auf, wenn man sie braucht.
#>

function ConvertTo-S3Ziel {
    [CmdletBinding()]
    param(
        # 's3://eimer' oder 's3://eimer/ein/praefix' -- mit oder ohne
        # abschliessenden Schraegstrich.
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$Dateiname
    )

    if ($Uri -notlike 's3://*') {
        throw "'$Uri' ist keine S3-URI. Erwartet wird etwa 's3://ata-sicherung/'."
    }

    $ohnePraefix = $Uri.Substring(5).Trim('/')
    if (-not $ohnePraefix) {
        throw "'$Uri' nennt keinen Eimer."
    }

    # Begrenzung auf zwei Teile: Der Eimer ist alles bis zum ersten
    # Schraegstrich, der Rest ist Praefix und darf selbst Schraegstriche
    # enthalten.
    $teile = $ohnePraefix.Split('/', 2)
    $eimer = $teile[0]
    $praefix = if ($teile.Count -gt 1) { $teile[1].Trim('/') } else { '' }

    $schluessel = if ($praefix) { "$praefix/$Dateiname" } else { $Dateiname }

    return [pscustomobject]@{
        Eimer       = $eimer
        Schluessel  = $schluessel
    }
}
