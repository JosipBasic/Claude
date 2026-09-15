# Update-ADUserDepartment.ps1

Bulk-updates the `Department` attribute on Active Directory users from a CSV
file, using the RSAT `ActiveDirectory` PowerShell module.

## Requirements

- Windows with the **ActiveDirectory** module (RSAT: Active Directory Domain
  Services and Lite Directory Services Tools), or run from a domain
  controller / management server that already has it.
- An account with permission to modify the target users' attributes.

## CSV format

Header row required, default column names `SamAccountName` and `Department`:

```csv
SamAccountName,Department
jdoe,Sales
bsmith,Engineering
```

## Usage

```powershell
# Preview changes without touching AD
.\Update-ADUserDepartment.ps1 -CsvPath .\users.csv -WhatIf

# Apply changes and write a per-row result log
.\Update-ADUserDepartment.ps1 -CsvPath .\users.csv -LogPath .\update-log.csv

# Look users up by UserPrincipalName instead, against a specific DC
.\Update-ADUserDepartment.ps1 -CsvPath .\users.csv `
    -IdentifierColumn UserPrincipalName -Server dc01.corp.example.com

# Run as a different account
.\Update-ADUserDepartment.ps1 -CsvPath .\users.csv -Credential (Get-Credential)
```

`-IdentifierColumn` also accepts `EmployeeID`, or any other single-valued AD
attribute name if your CSV keys on something else.

Each row is processed independently and reports one of: `Updated`,
`Unchanged` (already correct), `NotFound`, `AmbiguousMatch` (more than one
user matched), `Skipped` (blank identifier), or `Error`. A summary count is
printed at the end, and the full per-row results are returned on the
pipeline (and optionally written to `-LogPath` as CSV).
