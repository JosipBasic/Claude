from app.ad_client import ADError


def test_create_and_search_ou(mock_client):
    dn = mock_client.create_ou("Marketing")
    assert dn == "OU=Marketing,DC=corp,DC=example,DC=com"

    ous = mock_client.list_ous()
    names = {ou.name for ou in ous}
    assert "Marketing" in names
    assert "Sales" in names


def test_create_user_and_search(mock_client):
    dn = mock_client.create_user(
        sam_account_name="jdoe",
        given_name="Jane",
        surname="Doe",
        mail="jdoe@example.com",
    )
    assert dn == "CN=Jane Doe,DC=corp,DC=example,DC=com"

    users = mock_client.search_users()
    assert len(users) == 1
    assert users[0].sam_account_name == "jdoe"
    assert users[0].enabled is True


def test_create_disabled_user(mock_client):
    mock_client.create_user(
        sam_account_name="disabled1",
        given_name="Dis",
        surname="Abled",
        mail="",
        enabled=False,
    )
    users = mock_client.search_users(query="disabled1")
    assert len(users) == 1
    assert users[0].enabled is False


def test_disable_user(mock_client):
    dn = mock_client.create_user(
        sam_account_name="tosser",
        given_name="To",
        surname="Sser",
        mail="",
    )
    assert mock_client.search_users(query="tosser")[0].enabled is True

    mock_client.disable_user(dn)
    assert mock_client.search_users(query="tosser")[0].enabled is False


def test_bulk_disable_users(mock_client):
    dns = [
        mock_client.create_user(sam_account_name=f"bulk{i}", given_name="B", surname=str(i), mail="")
        for i in range(3)
    ]
    errors = mock_client.bulk_disable_users(dns)
    assert errors == {}
    for user in mock_client.search_users():
        assert user.enabled is False


def test_bulk_disable_reports_errors_for_bad_dn(mock_client):
    good_dn = mock_client.create_user(sam_account_name="ok1", given_name="O", surname="K", mail="")
    bad_dn = "CN=doesnotexist,DC=corp,DC=example,DC=com"

    errors = mock_client.bulk_disable_users([good_dn, bad_dn])
    assert good_dn not in errors
    assert bad_dn in errors


def test_move_user_to_ou(mock_client):
    ou_dn = mock_client.create_ou("Disabled Accounts")
    user_dn = mock_client.create_user(sam_account_name="mover", given_name="Mo", surname="Ver", mail="")

    new_dn = mock_client.move_object(user_dn, ou_dn)
    assert new_dn == f"CN=Mo Ver,{ou_dn}"

    users = mock_client.search_users()
    assert users[0].dn == new_dn
    assert users[0].ou == ou_dn


def test_bulk_move_objects(mock_client):
    ou_dn = mock_client.create_ou("Archive")
    dns = [
        mock_client.create_user(sam_account_name=f"arc{i}", given_name="A", surname=str(i), mail="")
        for i in range(2)
    ]
    errors = mock_client.bulk_move_objects(dns, ou_dn)
    assert errors == {}
    for user in mock_client.search_users():
        assert user.ou == ou_dn


def test_disable_and_move_combo(mock_client):
    ou_dn = mock_client.create_ou("Leavers")
    dn = mock_client.create_user(sam_account_name="leaver1", given_name="Leave", surname="R", mail="")

    mock_client.disable_user(dn)
    new_dn = mock_client.move_object(dn, ou_dn)

    user = mock_client.search_users()[0]
    assert user.dn == new_dn
    assert user.enabled is False
    assert user.ou == ou_dn
