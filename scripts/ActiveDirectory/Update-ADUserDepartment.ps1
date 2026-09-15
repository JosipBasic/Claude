<#
.SYNOPSIS
    Bulk-updates the Department attribute of Active Directory users from a CSV file.

.DESCRIPTION
    Reads a CSV file containing a user identifier column (SamAccountName by default)
    and a Department column, then sets the Department attribute on each matching AD
    user via Set-ADUser. Rows are processed independently: a failure on one row is
    logged and does not stop the rest of the run.

    Requires the ActiveDirectory PowerShell module (RSAT: Active Directory module),
    and an account with permission to modify the target users.

.PARAMETER CsvPath
    Path to the input CSV file.

.PARAMETER IdentifierColumn
    Name of the CSV column that identifies each user. Defaults to "SamAccountName".
    Use "UserPrincipalName" or "EmployeeID" if that's what your CSV keys on
    (EmployeeID is looked up via the ad-native EmployeeID attribute).

.PARAMETER DepartmentColumn
    Name of the CSV column holding the new Department value. Defaults to "Department".

.PARAMETER Delimiter
    CSV field delimiter. Defaults to ",".

.PARAMETER LogPath
    Optional path to write a CSV log of per-row results (Identifier, OldDepartment,
    NewDepartment, Status, Message). If omitted, results are only written to the
    console and the pipeline output.

.PARAMETER Server
    Optional domain controller / AD DS instance to target (passed to -Server on the
    underlying cmdlets).

.PARAMETER Credential
    Optional PSCredential to run the AD operations as a different account.

.EXAMPLE
    .\Update-ADUserDepartment.ps1 -CsvPath .\users.csv -WhatIf

    Preview what would change without modifying AD. CSV must have
    SamAccountName,Department columns.

.EXAMPLE
    .\Update-ADUserDepartment.ps1 -CsvPath .\users.csv -LogPath .\update-log.csv

    Applies the updates and writes a per-row result log.

.EXAMPLE
    .\Update-ADUserDepartment.ps1 -CsvPath .\users.csv -IdentifierColumn UserPrincipalName -Server dc01.corp.example.com

    Looks users up by UserPrincipalName against a specific domain controller.

.NOTES
    CSV format (header required), e.g.:

        SamAccountName,Department
        jdoe,Sales
        bsmith,Engineering
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$CsvPath,

    [Parameter()]
    [string]$IdentifierColumn = 'SamAccountName',

    [Parameter()]
    [string]$DepartmentColumn = 'Department',

    [Parameter()]
    [string]$Delimiter = ',',

    [Parameter()]
    [string]$LogPath,

    [Parameter()]
    [string]$Server,

    [Parameter()]
    [System.Management.Automation.PSCredential]$Credential
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Get-Module -ListAvailable -Name ActiveDirectory)) {
    throw "The ActiveDirectory module is not available. Install RSAT: Active Directory Domain Services and Lite Directory Services Tools, then re-run this script."
}
Import-Module ActiveDirectory -ErrorAction Stop

$rows = Import-Csv -LiteralPath $CsvPath -Delimiter $Delimiter
if (-not $rows) {
    Write-Warning "No rows found in '$CsvPath'."
    return
}

$firstRow = $rows[0]
foreach ($col in @($IdentifierColumn, $DepartmentColumn)) {
    if (-not ($firstRow.PSObject.Properties.Name -contains $col)) {
        throw "CSV is missing required column '$col'. Found columns: $($firstRow.PSObject.Properties.Name -join ', ')"
    }
}

$adCmdletParams = @{}
if ($Server) { $adCmdletParams['Server'] = $Server }
if ($Credential) { $adCmdletParams['Credential'] = $Credential }

$results = [System.Collections.Generic.List[pscustomobject]]::new()
$rowNumber = 1

foreach ($row in $rows) {
    $rowNumber++
    $identifierValue = ($row.$IdentifierColumn | Out-String).Trim()
    $newDepartment = ($row.$DepartmentColumn | Out-String).Trim()

    if (-not $identifierValue) {
        $results.Add([pscustomobject]@{
            Row            = $rowNumber
            Identifier     = $identifierValue
            OldDepartment  = $null
            NewDepartment  = $newDepartment
            Status         = 'Skipped'
            Message        = "Empty '$IdentifierColumn' value"
        })
        Write-Warning "Row $rowNumber : empty '$IdentifierColumn' value, skipping."
        continue
    }

    try {
        $filter = if ($IdentifierColumn -eq 'SamAccountName') {
            "SamAccountName -eq '$identifierValue'"
        }
        elseif ($IdentifierColumn -eq 'UserPrincipalName') {
            "UserPrincipalName -eq '$identifierValue'"
        }
        elseif ($IdentifierColumn -eq 'EmployeeID') {
            "EmployeeID -eq '$identifierValue'"
        }
        else {
            "$IdentifierColumn -eq '$identifierValue'"
        }

        $adUser = Get-ADUser -Filter $filter -Properties Department @adCmdletParams

        if (-not $adUser) {
            $results.Add([pscustomobject]@{
                Row           = $rowNumber
                Identifier    = $identifierValue
                OldDepartment = $null
                NewDepartment = $newDepartment
                Status        = 'NotFound'
                Message       = "No AD user matched $IdentifierColumn '$identifierValue'"
            })
            Write-Warning "Row $rowNumber : no AD user matched $IdentifierColumn '$identifierValue'."
            continue
        }

        if ($adUser -is [array]) {
            $results.Add([pscustomobject]@{
                Row           = $rowNumber
                Identifier    = $identifierValue
                OldDepartment = $null
                NewDepartment = $newDepartment
                Status        = 'AmbiguousMatch'
                Message       = "$($adUser.Count) AD users matched $IdentifierColumn '$identifierValue'"
            })
            Write-Warning "Row $rowNumber : $($adUser.Count) AD users matched $IdentifierColumn '$identifierValue', skipping."
            continue
        }

        $oldDepartment = $adUser.Department

        if ($oldDepartment -eq $newDepartment) {
            $results.Add([pscustomobject]@{
                Row           = $rowNumber
                Identifier    = $identifierValue
                OldDepartment = $oldDepartment
                NewDepartment = $newDepartment
                Status        = 'Unchanged'
                Message       = 'Department already up to date'
            })
            continue
        }

        if ($PSCmdlet.ShouldProcess($adUser.DistinguishedName, "Set Department: '$oldDepartment' -> '$newDepartment'")) {
            Set-ADUser -Identity $adUser -Department $newDepartment @adCmdletParams
            $results.Add([pscustomobject]@{
                Row           = $rowNumber
                Identifier    = $identifierValue
                OldDepartment = $oldDepartment
                NewDepartment = $newDepartment
                Status        = 'Updated'
                Message       = ''
            })
            Write-Verbose "Row $rowNumber : updated $identifierValue ('$oldDepartment' -> '$newDepartment')."
        }
        else {
            $results.Add([pscustomobject]@{
                Row           = $rowNumber
                Identifier    = $identifierValue
                OldDepartment = $oldDepartment
                NewDepartment = $newDepartment
                Status        = 'WhatIf'
                Message       = 'No changes made (-WhatIf)'
            })
        }
    }
    catch {
        $results.Add([pscustomobject]@{
            Row           = $rowNumber
            Identifier    = $identifierValue
            OldDepartment = $null
            NewDepartment = $newDepartment
            Status        = 'Error'
            Message       = $_.Exception.Message
        })
        Write-Warning "Row $rowNumber : error updating '$identifierValue' - $($_.Exception.Message)"
    }
}

if ($LogPath) {
    $results | Export-Csv -LiteralPath $LogPath -NoTypeInformation -Delimiter $Delimiter
    Write-Host "Log written to '$LogPath'."
}

$summary = $results | Group-Object Status | Select-Object Name, Count
Write-Host ""
Write-Host "Summary:"
$summary | ForEach-Object { Write-Host ("  {0,-15} {1}" -f $_.Name, $_.Count) }

$results
