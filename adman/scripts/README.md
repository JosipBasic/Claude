# Standalone AD scripts

PowerShell scripts meant to run directly on a domain controller (or any
host with the ActiveDirectory RSAT module), independent of the `adman`
Flask app.

## Set-ADUserDepartment.ps1

Bulk-updates the `department` attribute on AD user accounts from a CSV.

**CSV format** (header row required), default location
`C:\Temp\department_updates.csv`:

```
SamAccountName,Department
jdoe,Sales
bsmith,Engineering
```

Rows with a blank `Department` are skipped (to avoid accidentally clearing
the attribute) rather than applied.

**Usage** (run on the domain controller as an account with write access to
the target users):

```powershell
# Dry run first - shows what would change without modifying AD
.\Set-ADUserDepartment.ps1 -CsvPath C:\Temp\department_updates.csv -WhatIf

# Apply the changes
.\Set-ADUserDepartment.ps1 -CsvPath C:\Temp\department_updates.csv
```

Each run writes a timestamped log (`Set-ADUserDepartment_<timestamp>.log`)
and, if any rows fail, a `Set-ADUserDepartment_failures_<timestamp>.csv`
next to the input CSV, both in the same folder as the input file.
