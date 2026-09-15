import io

from app import create_app
from app.routes import _CONNECTIONS


def _login(client, mock_client):
    with client.session_transaction() as sess:
        sess["conn_token"] = "test-token"
    _CONNECTIONS["test-token"] = mock_client


def test_redirects_to_connect_when_not_logged_in():
    app = create_app({"TESTING": True})
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/connect" in resp.headers["Location"]


def test_dashboard_after_connect(mock_client):
    app = create_app({"TESTING": True})
    client = app.test_client()
    _login(client, mock_client)

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"Organizational Units" in resp.data


def test_users_page_lists_created_user(mock_client):
    mock_client.create_user(sam_account_name="wpage", given_name="Web", surname="Page", mail="w@example.com")

    app = create_app({"TESTING": True})
    client = app.test_client()
    _login(client, mock_client)

    resp = client.get("/users")
    assert resp.status_code == 200
    assert b"wpage" in resp.data


def test_users_export_csv(mock_client):
    mock_client.create_user(sam_account_name="exportme", given_name="Ex", surname="Port", mail="")

    app = create_app({"TESTING": True})
    client = app.test_client()
    _login(client, mock_client)

    resp = client.get("/users/export")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert b"exportme" in resp.data


def test_bulk_disable_via_route(mock_client):
    dn = mock_client.create_user(sam_account_name="viaroute", given_name="Via", surname="Route", mail="")

    app = create_app({"TESTING": True})
    client = app.test_client()
    _login(client, mock_client)

    resp = client.post("/users/bulk-disable", data={"selected_dn": [dn]}, follow_redirects=True)
    assert resp.status_code == 200
    assert mock_client.search_users(query="viaroute")[0].enabled is False


def test_create_ou_via_route(mock_client):
    app = create_app({"TESTING": True})
    client = app.test_client()
    _login(client, mock_client)

    resp = client.post(
        "/ous", data={"name": "Contractors", "parent_dn": mock_client.settings.base_dn}, follow_redirects=True
    )
    assert resp.status_code == 200
    names = {ou.name for ou in mock_client.list_ous()}
    assert "Contractors" in names


def test_import_users_preview_and_commit(mock_client):
    app = create_app({"TESTING": True, "SECRET_KEY": "test"})
    client = app.test_client()
    _login(client, mock_client)

    csv_content = "sam_account_name,given_name,surname,mail\nnewbie,New,Bie,newbie@example.com\n"
    data = {
        "stage": "preview",
        "default_ou": "",
        "csv_file": (io.BytesIO(csv_content.encode()), "users.csv"),
    }
    resp = client.post("/users/import", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert b"newbie" in resp.data

    resp = client.post("/users/import", data={"stage": "commit", "default_ou": ""}, follow_redirects=True)
    assert resp.status_code == 200
    assert mock_client.search_users(query="newbie")[0].sam_account_name == "newbie"
