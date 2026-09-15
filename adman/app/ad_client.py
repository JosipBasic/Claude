"""Thin wrapper around ldap3 for the Active Directory operations this app needs.

Everything the web UI does to AD (search, create OU, create/disable/move user)
goes through this module so the routes stay free of LDAP details.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ldap3 import (
    ALL_ATTRIBUTES,
    MODIFY_REPLACE,
    SUBTREE,
    SYNC,
    Connection,
    Server,
    Tls,
)
from ldap3.core.exceptions import LDAPException

# userAccountControl bit flags we care about
UAC_ACCOUNTDISABLE = 0x0002
UAC_NORMAL_ACCOUNT = 0x0200


class ADError(Exception):
    """Raised for any AD/LDAP operation failure, with a human-readable message."""


@dataclass
class ConnectionSettings:
    server: str
    base_dn: str
    bind_dn: str
    password: str
    use_ssl: bool = True
    port: int | None = None


@dataclass
class ADUser:
    dn: str
    sam_account_name: str
    display_name: str
    given_name: str
    surname: str
    mail: str
    user_principal_name: str
    enabled: bool
    ou: str
    when_created: str
    member_of: list[str] = field(default_factory=list)

    def to_row(self) -> dict:
        return {
            "sAMAccountName": self.sam_account_name,
            "displayName": self.display_name,
            "givenName": self.given_name,
            "sn": self.surname,
            "mail": self.mail,
            "userPrincipalName": self.user_principal_name,
            "distinguishedName": self.dn,
            "enabled": self.enabled,
            "ou": self.ou,
            "whenCreated": self.when_created,
            "memberOf": ";".join(self.member_of),
        }


@dataclass
class ADComputer:
    dn: str
    name: str
    dns_hostname: str
    operating_system: str
    operating_system_version: str
    enabled: bool
    ou: str
    when_created: str

    def to_row(self) -> dict:
        return {
            "name": self.name,
            "dNSHostName": self.dns_hostname,
            "operatingSystem": self.operating_system,
            "operatingSystemVersion": self.operating_system_version,
            "distinguishedName": self.dn,
            "enabled": self.enabled,
            "ou": self.ou,
            "whenCreated": self.when_created,
        }


@dataclass
class OUNode:
    dn: str
    name: str
    depth: int


def _parent_dn(dn: str) -> str:
    """Return the DN of the immediate parent container."""
    parts = dn.split(",")
    return ",".join(parts[1:])


def _ou_from_dn(dn: str) -> str:
    return _parent_dn(dn)


def _uac_to_enabled(uac_value) -> bool:
    try:
        uac = int(uac_value)
    except (TypeError, ValueError):
        return True
    return not bool(uac & UAC_ACCOUNTDISABLE)


class ADClient:
    """A connected session to one Active Directory / LDAP server."""

    def __init__(self, settings: ConnectionSettings, connection: Connection | None = None):
        self.settings = settings
        if connection is not None:
            self._conn = connection
        else:
            tls = Tls() if settings.use_ssl else None
            server = Server(
                settings.server,
                port=settings.port,
                use_ssl=settings.use_ssl,
                tls=tls,
                get_info="ALL",
            )
            self._conn = Connection(
                server,
                user=settings.bind_dn,
                password=settings.password,
                client_strategy=SYNC,
                auto_bind=True,
                raise_exceptions=True,
            )

    @classmethod
    def connect(cls, settings: ConnectionSettings) -> "ADClient":
        try:
            return cls(settings)
        except LDAPException as exc:
            raise ADError(f"Could not bind to AD server: {exc}") from exc

    def close(self) -> None:
        try:
            self._conn.unbind()
        except LDAPException:
            pass

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def _search(self, base_dn: str, filter_: str, attributes) -> list[dict]:
        # Note: connection.search()'s own boolean return is False whenever a
        # search finds zero entries, even on a fully successful search - so
        # success is determined from the LDAP result code instead.
        try:
            self._conn.search(
                search_base=base_dn,
                search_filter=filter_,
                search_scope=SUBTREE,
                attributes=attributes,
            )
        except LDAPException as exc:
            raise ADError(f"Search failed: {exc}") from exc
        if self._conn.result.get("result") != 0:
            raise ADError(f"Search failed: {self._conn.result}")
        return [entry for entry in self._conn.response if entry.get("type") == "searchResEntry"]

    def search_users(self, query: str | None = None, base_dn: str | None = None) -> list[ADUser]:
        # Computer accounts are also objectClass=user in AD's schema (computer
        # is a subclass of user), so they're excluded explicitly rather than
        # relying on objectCategory, which is populated by the AD DSA itself
        # and isn't necessarily present right after a raw LDAP add.
        base = base_dn or self.settings.base_dn
        filter_ = "(&(objectClass=user)(!(objectClass=computer)))"
        if query:
            escaped = query.replace("*", "")
            filter_ = (
                "(&(objectClass=user)(!(objectClass=computer))(|"
                f"(sAMAccountName=*{escaped}*)(displayName=*{escaped}*)(mail=*{escaped}*)))"
            )
        entries = self._search(base, filter_, ALL_ATTRIBUTES)
        users = []
        for entry in entries:
            attrs = entry["attributes"]
            dn = entry["dn"]
            users.append(
                ADUser(
                    dn=dn,
                    sam_account_name=_first(attrs.get("sAMAccountName")),
                    display_name=_first(attrs.get("displayName")),
                    given_name=_first(attrs.get("givenName")),
                    surname=_first(attrs.get("sn")),
                    mail=_first(attrs.get("mail")),
                    user_principal_name=_first(attrs.get("userPrincipalName")),
                    enabled=_uac_to_enabled(_first(attrs.get("userAccountControl"))),
                    ou=_ou_from_dn(dn),
                    when_created=str(_first(attrs.get("whenCreated")) or ""),
                    member_of=list(attrs.get("memberOf") or []),
                )
            )
        return users

    def search_computers(self, query: str | None = None, base_dn: str | None = None) -> list[ADComputer]:
        base = base_dn or self.settings.base_dn
        filter_ = "(objectClass=computer)"
        if query:
            escaped = query.replace("*", "")
            filter_ = f"(&(objectClass=computer)(|(name=*{escaped}*)(dNSHostName=*{escaped}*)))"
        entries = self._search(base, filter_, ALL_ATTRIBUTES)
        computers = []
        for entry in entries:
            attrs = entry["attributes"]
            dn = entry["dn"]
            computers.append(
                ADComputer(
                    dn=dn,
                    name=_first(attrs.get("name")),
                    dns_hostname=_first(attrs.get("dNSHostName")),
                    operating_system=_first(attrs.get("operatingSystem")),
                    operating_system_version=_first(attrs.get("operatingSystemVersion")),
                    enabled=_uac_to_enabled(_first(attrs.get("userAccountControl"))),
                    ou=_ou_from_dn(dn),
                    when_created=str(_first(attrs.get("whenCreated")) or ""),
                )
            )
        return computers

    def list_ous(self, base_dn: str | None = None) -> list[OUNode]:
        base = base_dn or self.settings.base_dn
        entries = self._search(base, "(objectClass=organizationalUnit)", ["ou", "distinguishedName"])
        nodes = []
        for entry in entries:
            dn = entry["dn"]
            name = _first(entry["attributes"].get("ou")) or dn.split(",")[0].split("=", 1)[-1]
            depth = dn.count(",") - base.count(",")
            nodes.append(OUNode(dn=dn, name=name, depth=max(depth, 0)))
        nodes.sort(key=lambda n: n.dn.lower())
        return nodes

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def create_ou(self, name: str, parent_dn: str | None = None) -> str:
        parent = parent_dn or self.settings.base_dn
        new_dn = f"OU={name},{parent}"
        try:
            success = self._conn.add(
                new_dn, ["top", "organizationalUnit"], {"ou": name}
            )
        except LDAPException as exc:
            raise ADError(f"Could not create OU '{name}': {exc}") from exc
        if not success:
            raise ADError(f"Could not create OU '{name}': {self._conn.result}")
        return new_dn

    def create_user(
        self,
        sam_account_name: str,
        given_name: str,
        surname: str,
        mail: str,
        ou_dn: str | None = None,
        upn_suffix: str | None = None,
        enabled: bool = True,
        password: str | None = None,
    ) -> str:
        target_ou = ou_dn or self.settings.base_dn
        display_name = f"{given_name} {surname}".strip()
        cn = display_name or sam_account_name
        new_dn = f"CN={cn},{target_ou}"
        upn = f"{sam_account_name}@{upn_suffix}" if upn_suffix else sam_account_name

        uac = UAC_NORMAL_ACCOUNT if enabled else (UAC_NORMAL_ACCOUNT | UAC_ACCOUNTDISABLE)
        attributes = {
            "cn": cn,
            "sAMAccountName": sam_account_name,
            "givenName": given_name,
            "sn": surname,
            "displayName": display_name,
            "userPrincipalName": upn,
            "userAccountControl": uac,
        }
        if mail:
            attributes["mail"] = mail

        try:
            success = self._conn.add(
                new_dn,
                ["top", "person", "organizationalPerson", "user"],
                attributes,
            )
        except LDAPException as exc:
            raise ADError(f"Could not create user '{sam_account_name}': {exc}") from exc
        if not success:
            raise ADError(f"Could not create user '{sam_account_name}': {self._conn.result}")

        if password:
            self.set_password(new_dn, password)

        return new_dn

    def set_password(self, dn: str, password: str) -> None:
        """Set a user's password. Requires an SSL/TLS (LDAPS) connection on real AD."""
        encoded = f'"{password}"'.encode("utf-16-le")
        try:
            success = self._conn.modify(
                dn, {"unicodePwd": [(MODIFY_REPLACE, [encoded])]}
            )
        except LDAPException as exc:
            raise ADError(f"Could not set password for {dn}: {exc}") from exc
        if not success:
            raise ADError(f"Could not set password for {dn}: {self._conn.result}")

    def _set_account_disabled(self, dn: str, disabled: bool) -> None:
        entries = self._search(dn, "(objectClass=*)", ["userAccountControl"])
        current = 0
        if entries:
            current = int(_first(entries[0]["attributes"].get("userAccountControl")) or 0)
        else:
            current = UAC_NORMAL_ACCOUNT
        if disabled:
            new_value = current | UAC_ACCOUNTDISABLE
        else:
            new_value = current & ~UAC_ACCOUNTDISABLE
        try:
            success = self._conn.modify(
                dn, {"userAccountControl": [(MODIFY_REPLACE, [new_value])]}
            )
        except LDAPException as exc:
            raise ADError(f"Could not update account state for {dn}: {exc}") from exc
        if not success:
            raise ADError(f"Could not update account state for {dn}: {self._conn.result}")

    def disable_user(self, dn: str) -> None:
        self._set_account_disabled(dn, True)

    def enable_user(self, dn: str) -> None:
        self._set_account_disabled(dn, False)

    def bulk_disable_users(self, dns: Iterable[str]) -> dict[str, str]:
        """Disable each DN; returns a map of dn -> error message for any that failed."""
        errors: dict[str, str] = {}
        for dn in dns:
            try:
                self.disable_user(dn)
            except ADError as exc:
                errors[dn] = str(exc)
        return errors

    def move_object(self, dn: str, target_ou_dn: str) -> str:
        rdn = dn.split(",", 1)[0]
        try:
            success = self._conn.modify_dn(
                dn, rdn, new_superior=target_ou_dn
            )
        except LDAPException as exc:
            raise ADError(f"Could not move {dn}: {exc}") from exc
        if not success:
            raise ADError(f"Could not move {dn}: {self._conn.result}")
        return f"{rdn},{target_ou_dn}"

    def bulk_move_objects(self, dns: Iterable[str], target_ou_dn: str) -> dict[str, str]:
        """Move each DN into target_ou_dn; returns a map of dn -> error message for failures."""
        errors: dict[str, str] = {}
        for dn in dns:
            try:
                self.move_object(dn, target_ou_dn)
            except ADError as exc:
                errors[dn] = str(exc)
        return errors


def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value
