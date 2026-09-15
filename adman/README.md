# AD Manager

A small Flask web app for day-to-day Active Directory administration:

- Browse and search **users** and **computers**
- Export users/computers to CSV
- **Import users from CSV** (preview before committing, per-row error reporting)
- **Bulk disable** users and **bulk move** them into a target OU (including a combined "disable & move" action, e.g. for offboarding)
- **Create new OUs** (folders) anywhere in the directory tree

It talks to AD over LDAP/LDAPS using [`ldap3`](https://ldap3.readthedocs.io/) — no
Windows/RSAT tools or PowerShell required, so it runs from Linux, macOS, or Windows.

## Requirements

- Python 3.10+
- Network access to a domain controller (LDAPS on port 636 strongly recommended;
  plain LDAP on 389 works for browsing but AD will reject password-setting
  operations over an unencrypted connection)
- An AD account with permission to perform the operations you plan to use
  (reading is enough to browse/export; creating/modifying objects needs write
  access to the relevant OUs)

## Setup

```bash
cd adman
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit SECRET_KEY
```

## Running

```bash
source .venv/bin/activate
export $(cat .env | xargs)   # or use python-dotenv / your process manager
python run.py
```

Then open http://127.0.0.1:5000 and fill in the connection form:

| Field    | Example                                                |
|----------|---------------------------------------------------------|
| Server   | `dc01.corp.example.com`                                  |
| Port     | `636` (LDAPS) or `389` (LDAP) — leave blank for the default |
| Base DN  | `DC=corp,DC=example,DC=com`                              |
| Bind DN  | `CN=svc-admanager,CN=Users,DC=corp,DC=example,DC=com` (or `user@corp.example.com`) |
| Password | the account's password                                   |

Credentials are held only in this process's memory for the life of the
session (never written to disk or logged) and are dropped on Disconnect or
process restart. This is designed as a single-admin internal tool — it does
not implement multi-user authentication of its own, so run it somewhere only
trusted admins can reach (e.g. localhost, or behind your own auth proxy/VPN),
and use a dedicated service account scoped to the least privilege you need.

## CSV import format

Upload a CSV with these columns (only `sam_account_name` is required):

```
sam_account_name,given_name,surname,mail,ou,password,enabled
jdoe,Jane,Doe,jdoe@example.com,,,true
bsmith,Bob,Smith,bsmith@example.com,"OU=Sales,DC=corp,DC=example,DC=com",,false
```

- `ou`: distinguished name of the target OU for that row; falls back to the
  "Default OU" chosen on the import page, or the connection's base DN.
- `password`: optional; setting a password requires an LDAPS connection.
- `enabled`: `true`/`false` (or `1`/`0`, `yes`/`no`); defaults to `true`.

The import page shows a preview with per-row validation errors before any
changes are made to AD — nothing is created until you confirm.

## Bulk disable & move

On the Users page, check the rows you want to act on, pick a target OU from
the dropdown, then choose **Disable Selected**, **Move Selected**, or
**Disable & Move Selected** (handy for offboarding: disable the account and
move it into e.g. an "OU=Disabled Accounts" OU in one step). Any per-object
failures are reported without rolling back the rest of the batch.

## Creating OUs

The **OUs** page lists existing organizational units and lets you create a
new one under any existing OU or directly under the base DN.

## Packaging as a Windows .exe

You can build a standalone `adman.exe` (no Python install required on the
target server) with [PyInstaller](https://pyinstaller.org/). This must be
done **on a Windows machine** — PyInstaller does not cross-compile, so
building on Linux/macOS won't produce a working Windows binary. Build on
the Windows Server itself, or on any Windows box with the same
architecture/bitness, then copy the output over.

```cmd
cd adman
build_windows.bat
```

This creates `dist\adman\adman.exe` plus its supporting files in
`dist\adman\`. Copy the whole `dist\adman\` folder to the server — the
`.exe` needs the files alongside it, it isn't fully self-contained.

To run it:

```cmd
cd dist\adman
set SECRET_KEY=<a real secret, see .env.example>
set ADMAN_PORT=5000
adman.exe
```

When run as a frozen `.exe`, adman serves over
[waitress](https://docs.pylonsproject.org/projects/waitress/) (a
production-ready WSGI server) instead of Flask's development server.
`ADMAN_HOST` (default `127.0.0.1`) and `ADMAN_PORT` (default `5000`)
control where it listens — as noted above, this tool has no built-in
multi-user auth, so keep it bound to localhost or a trusted network unless
you put it behind your own auth proxy/VPN.

To run it as a background Windows service instead of a console app, wrap
it with something like [NSSM](https://nssm.cc/) (`nssm install adman
C:\path\to\dist\adman\adman.exe`) or Windows' own `sc create`.

If you change `requirements.txt` or add new dependencies, re-run
`build_windows.bat` to rebuild.

## Development / tests

Tests run against an in-memory mock LDAP server (via `ldap3`'s `MOCK_SYNC`
strategy), so they don't need a real AD environment:

```bash
pip install -r requirements-dev.txt
pytest
```

## Notes & limitations

- This app assumes a single admin uses it at a time per process (in-memory
  connection registry); it's not built for multi-tenant/shared deployment.
- Setting a password (`unicodePwd`) requires LDAPS; over plain LDAP, AD
  itself will reject the operation.
- Deleting users/computers or OUs is intentionally not implemented, to keep
  the destructive surface area of this tool limited to disable/move/create.
