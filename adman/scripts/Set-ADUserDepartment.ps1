#Requires -Version 5.1
#Requires -Modules ActiveDirectory

<#
Bulk-updates the "department" attribute on AD user accounts from a CSV.
Run directly on a domain controller (or any host with the ActiveDirectory
RSAT module) as an account with write access to the target users.

CSV format (header row required), default location C:\Temp\department_updates.csv:

    SamAccountName,Department
    jdoe,Sales
    bsmith,Engineering

Rows with a blank Department are skipped (to avoid accidentally clearing the
attribute) and reported in the summary.

Usage:
    .\Set-ADUserDepartment.ps1                      # uses C:\Temp\department_updates.csv
    .\Set-ADUserDepartment.ps1 -CsvPath C:\Temp\deps.csv
    .\Set-ADUserDepartment.ps1 -WhatIf               # dry run, no changes made
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$CsvPath = 'C:\Temp\department_updates.csv',
    [string]$Server
)

if (-not (Test-Path -LiteralPath $CsvPath)) {
    throw "CSV file not found: $CsvPath"
}

Import-Module ActiveDirectory -ErrorAction Stop

$rows = Import-Csv -LiteralPath $CsvPath
if (-not $rows) {
    throw "CSV file is empty: $CsvPath"
}

$firstRow = $rows[0]
foreach ($required in 'SamAccountName', 'Department') {
    if (-not ($firstRow.PSObject.Properties.Name -contains $required)) {
        throw "CSV is missing required column '$required'. Found columns: $($firstRow.PSObject.Properties.Name -join ', ')"
    }
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$logPath = Join-Path (Split-Path -Path $CsvPath -Parent) "Set-ADUserDepartment_$timestamp.log"
$failuresPath = Join-Path (Split-Path -Path $CsvPath -Parent) "Set-ADUserDepartment_failures_$timestamp.csv"

$getADUserParams = @{}
$setADUserParams = @{}
if ($Server) {
    $getADUserParams['Server'] = $Server
    $setADUserParams['Server'] = $Server
}

$updated = 0
$skipped = 0
$failed = @()
$rowNum = 1

function Write-Log {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $Message"
    Write-Output $line
    Add-Content -LiteralPath $logPath -Value $line
}

Write-Log "Starting department update from '$CsvPath' ($($rows.Count) rows)"

foreach ($row in $rows) {
    $rowNum++
    $sam = ($row.SamAccountName | Out-String).Trim()
    $department = ($row.Department | Out-String).Trim()

    if (-not $sam) {
        Write-Log "Row $rowNum : skipped, empty SamAccountName"
        $skipped++
        continue
    }

    if (-not $department) {
        Write-Log "Row $rowNum ($sam): skipped, empty Department"
        $skipped++
        continue
    }

    try {
        $null = Get-ADUser -Identity $sam @getADUserParams -ErrorAction Stop
    }
    catch {
        Write-Log "Row $rowNum ($sam): FAILED, user not found: $($_.Exception.Message)"
        $failed += [pscustomobject]@{ SamAccountName = $sam; Department = $department; Error = "User not found: $($_.Exception.Message)" }
        continue
    }

    if ($PSCmdlet.ShouldProcess($sam, "Set Department = '$department'")) {
        try {
            Set-ADUser -Identity $sam -Department $department @setADUserParams -ErrorAction Stop
            Write-Log "Row $rowNum ($sam): updated Department = '$department'"
            $updated++
        }
        catch {
            Write-Log "Row $rowNum ($sam): FAILED, $($_.Exception.Message)"
            $failed += [pscustomobject]@{ SamAccountName = $sam; Department = $department; Error = $_.Exception.Message }
        }
    }
}

Write-Log "Done. Updated: $updated, Skipped: $skipped, Failed: $($failed.Count)"

if ($failed.Count -gt 0) {
    $failed | Export-Csv -LiteralPath $failuresPath -NoTypeInformation
    Write-Log "Failure details written to '$failuresPath'"
}
