from app.ad_client import ADComputer, ADUser
from app.csv_io import computers_to_csv, parse_user_import_csv, users_to_csv


def test_users_to_csv_round_trip():
    user = ADUser(
        dn="CN=Jane Doe,OU=Sales,DC=corp,DC=example,DC=com",
        sam_account_name="jdoe",
        display_name="Jane Doe",
        given_name="Jane",
        surname="Doe",
        mail="jdoe@example.com",
        user_principal_name="jdoe@example.com",
        enabled=True,
        ou="OU=Sales,DC=corp,DC=example,DC=com",
        when_created="20240101000000Z",
        member_of=["CN=Sales Team,DC=corp,DC=example,DC=com"],
    )
    csv_text = users_to_csv([user])
    assert "jdoe" in csv_text
    assert "Jane Doe" in csv_text
    assert "Sales Team" in csv_text


def test_computers_to_csv():
    computer = ADComputer(
        dn="CN=WKS01,OU=Workstations,DC=corp,DC=example,DC=com",
        name="WKS01",
        dns_hostname="wks01.corp.example.com",
        operating_system="Windows 11",
        operating_system_version="10.0",
        enabled=True,
        ou="OU=Workstations,DC=corp,DC=example,DC=com",
        when_created="20240101000000Z",
    )
    csv_text = computers_to_csv([computer])
    assert "WKS01" in csv_text
    assert "wks01.corp.example.com" in csv_text


def test_parse_user_import_csv_valid_rows():
    content = (
        "sam_account_name,given_name,surname,mail,ou,enabled\n"
        "jdoe,Jane,Doe,jdoe@example.com,,true\n"
        'bsmith,Bob,Smith,bsmith@example.com,"OU=Sales,DC=corp,DC=example,DC=com",false\n'
    )
    rows = parse_user_import_csv(content)
    assert len(rows) == 2
    assert rows[0].sam_account_name == "jdoe"
    assert rows[0].enabled is True
    assert rows[0].errors == []
    assert rows[1].enabled is False
    assert rows[1].ou == "OU=Sales,DC=corp,DC=example,DC=com"


def test_parse_user_import_csv_flags_missing_required_field():
    content = "sam_account_name,given_name,surname,mail\n,No,Sam,x@example.com\n"
    rows = parse_user_import_csv(content)
    assert len(rows) == 1
    assert rows[0].errors == ["sam_account_name is required"]
