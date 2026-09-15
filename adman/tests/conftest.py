import pytest
from ldap3 import ALL_ATTRIBUTES, MOCK_SYNC, OFFLINE_AD_2012_R2, Connection, Server

from app.ad_client import ADClient, ConnectionSettings

BASE_DN = "DC=corp,DC=example,DC=com"
ADMIN_DN = "CN=admin,DC=corp,DC=example,DC=com"


@pytest.fixture
def mock_client():
    """An ADClient backed by ldap3's in-memory mock server, pre-seeded with
    a base OU structure so tests exercise the same code paths as real AD."""
    server = Server("mock-dc", get_info=OFFLINE_AD_2012_R2)
    conn = Connection(server, user=ADMIN_DN, password="x", client_strategy=MOCK_SYNC)
    conn.open()
    conn.bind()

    conn.strategy.add_entry(
        BASE_DN, {"objectClass": ["top", "domain"], "dc": "corp"}
    )
    conn.strategy.add_entry(
        "OU=Sales,DC=corp,DC=example,DC=com",
        {"objectClass": ["top", "organizationalUnit"], "ou": "Sales"},
    )

    settings = ConnectionSettings(
        server="mock-dc",
        base_dn=BASE_DN,
        bind_dn=ADMIN_DN,
        password="x",
        use_ssl=False,
    )
    client = ADClient(settings, connection=conn)
    return client
