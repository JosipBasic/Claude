"""CSV export/import helpers for users and computers."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from .ad_client import ADComputer, ADUser

USER_EXPORT_FIELDS = [
    "sAMAccountName",
    "displayName",
    "givenName",
    "sn",
    "mail",
    "userPrincipalName",
    "distinguishedName",
    "enabled",
    "ou",
    "whenCreated",
    "memberOf",
]

COMPUTER_EXPORT_FIELDS = [
    "name",
    "dNSHostName",
    "operatingSystem",
    "operatingSystemVersion",
    "distinguishedName",
    "enabled",
    "ou",
    "whenCreated",
]

# Columns accepted on user import. sam_account_name is the only required one.
USER_IMPORT_FIELDS = [
    "sam_account_name",
    "given_name",
    "surname",
    "mail",
    "ou",
    "password",
    "enabled",
]


def users_to_csv(users: list[ADUser]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=USER_EXPORT_FIELDS)
    writer.writeheader()
    for user in users:
        writer.writerow(user.to_row())
    return buffer.getvalue()


def computers_to_csv(computers: list[ADComputer]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COMPUTER_EXPORT_FIELDS)
    writer.writeheader()
    for computer in computers:
        writer.writerow(computer.to_row())
    return buffer.getvalue()


@dataclass
class ImportRow:
    line_number: int
    sam_account_name: str
    given_name: str
    surname: str
    mail: str
    ou: str | None
    password: str | None
    enabled: bool
    errors: list[str]


def _parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "y")


def parse_user_import_csv(content: str) -> list[ImportRow]:
    """Parse an uploaded CSV of users to create. Missing required fields are
    recorded per-row as errors instead of raising, so the caller can show a
    preview of what will succeed/fail before committing anything to AD."""
    reader = csv.DictReader(io.StringIO(content))
    rows: list[ImportRow] = []
    for i, raw in enumerate(reader, start=2):  # header is line 1
        errors = []
        sam = (raw.get("sam_account_name") or raw.get("sAMAccountName") or "").strip()
        if not sam:
            errors.append("sam_account_name is required")
        given_name = (raw.get("given_name") or raw.get("givenName") or "").strip()
        surname = (raw.get("surname") or raw.get("sn") or "").strip()
        mail = (raw.get("mail") or "").strip()
        ou = (raw.get("ou") or "").strip() or None
        password = (raw.get("password") or "").strip() or None
        enabled = _parse_bool(raw.get("enabled"), default=True)
        rows.append(
            ImportRow(
                line_number=i,
                sam_account_name=sam,
                given_name=given_name,
                surname=surname,
                mail=mail,
                ou=ou,
                password=password,
                enabled=enabled,
                errors=errors,
            )
        )
    return rows
