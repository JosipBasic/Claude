from __future__ import annotations

import uuid

from flask import (
    Blueprint,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .ad_client import ADClient, ADError, ConnectionSettings
from .csv_io import computers_to_csv, parse_user_import_csv, users_to_csv

bp = Blueprint("main", __name__)

# In-memory connection registry: session token -> ADClient.
# This is a single-process, single-admin internal tool; connections are not
# persisted anywhere and are dropped on logout or process restart.
_CONNECTIONS: dict[str, ADClient] = {}


def _get_client() -> ADClient | None:
    token = session.get("conn_token")
    if not token:
        return None
    return _CONNECTIONS.get(token)


def _require_client():
    client = _get_client()
    if client is None:
        flash("Please connect to an Active Directory server first.", "error")
        return None
    return client


@bp.route("/")
def index():
    if _get_client() is None:
        return redirect(url_for("main.connect"))
    return redirect(url_for("main.dashboard"))


@bp.route("/connect", methods=["GET", "POST"])
def connect():
    if request.method == "POST":
        server = request.form.get("server", "").strip()
        port_raw = request.form.get("port", "").strip()
        base_dn = request.form.get("base_dn", "").strip()
        bind_dn = request.form.get("bind_dn", "").strip()
        password = request.form.get("password", "")
        use_ssl = request.form.get("use_ssl") == "on"

        if not server or not base_dn or not bind_dn:
            flash("Server, Base DN, and Bind DN are required.", "error")
            return render_template("connect.html", form=request.form)

        port = int(port_raw) if port_raw else None
        settings = ConnectionSettings(
            server=server,
            base_dn=base_dn,
            bind_dn=bind_dn,
            password=password,
            use_ssl=use_ssl,
            port=port,
        )
        try:
            client = ADClient.connect(settings)
        except ADError as exc:
            flash(str(exc), "error")
            return render_template("connect.html", form=request.form)

        # Replace any previous connection for this browser session.
        old_token = session.get("conn_token")
        if old_token and old_token in _CONNECTIONS:
            _CONNECTIONS.pop(old_token).close()

        token = uuid.uuid4().hex
        _CONNECTIONS[token] = client
        session["conn_token"] = token
        flash(f"Connected to {server}.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("connect.html", form={})


@bp.route("/disconnect", methods=["POST"])
def disconnect():
    token = session.pop("conn_token", None)
    if token and token in _CONNECTIONS:
        _CONNECTIONS.pop(token).close()
    flash("Disconnected.", "success")
    return redirect(url_for("main.connect"))


@bp.route("/dashboard")
def dashboard():
    client = _require_client()
    if client is None:
        return redirect(url_for("main.connect"))
    try:
        users = client.search_users()
        computers = client.search_computers()
        ous = client.list_ous()
    except ADError as exc:
        flash(str(exc), "error")
        return render_template("dashboard.html", counts=None)

    counts = {
        "users": len(users),
        "users_disabled": sum(1 for u in users if not u.enabled),
        "computers": len(computers),
        "ous": len(ous),
    }
    return render_template("dashboard.html", counts=counts, base_dn=client.settings.base_dn)


# ----------------------------------------------------------------------
# Users
# ----------------------------------------------------------------------
@bp.route("/users")
def users():
    client = _require_client()
    if client is None:
        return redirect(url_for("main.connect"))
    query = request.args.get("q", "").strip()
    try:
        user_list = client.search_users(query=query or None)
        ous = client.list_ous()
    except ADError as exc:
        flash(str(exc), "error")
        return render_template("users.html", users=[], ous=[], query=query)
    return render_template("users.html", users=user_list, ous=ous, query=query)


@bp.route("/users/export")
def users_export():
    client = _require_client()
    if client is None:
        return redirect(url_for("main.connect"))
    try:
        user_list = client.search_users()
    except ADError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.users"))
    csv_data = users_to_csv(user_list)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ad_users.csv"},
    )


@bp.route("/users/bulk-disable", methods=["POST"])
def users_bulk_disable():
    client = _require_client()
    if client is None:
        return redirect(url_for("main.connect"))
    dns = request.form.getlist("selected_dn")
    if not dns:
        flash("No users selected.", "error")
        return redirect(url_for("main.users"))
    errors = client.bulk_disable_users(dns)
    if errors:
        flash(f"Disabled {len(dns) - len(errors)} of {len(dns)} users. {len(errors)} failed.", "error")
        for dn, msg in errors.items():
            flash(f"{dn}: {msg}", "error")
    else:
        flash(f"Disabled {len(dns)} user(s).", "success")
    return redirect(url_for("main.users"))


@bp.route("/users/bulk-move", methods=["POST"])
def users_bulk_move():
    client = _require_client()
    if client is None:
        return redirect(url_for("main.connect"))
    dns = request.form.getlist("selected_dn")
    target_ou = request.form.get("target_ou", "").strip()
    if not dns:
        flash("No users selected.", "error")
        return redirect(url_for("main.users"))
    if not target_ou:
        flash("Choose a target OU to move selected users into.", "error")
        return redirect(url_for("main.users"))
    errors = client.bulk_move_objects(dns, target_ou)
    if errors:
        flash(f"Moved {len(dns) - len(errors)} of {len(dns)} users. {len(errors)} failed.", "error")
        for dn, msg in errors.items():
            flash(f"{dn}: {msg}", "error")
    else:
        flash(f"Moved {len(dns)} user(s) to {target_ou}.", "success")
    return redirect(url_for("main.users"))


@bp.route("/users/bulk-disable-and-move", methods=["POST"])
def users_bulk_disable_and_move():
    client = _require_client()
    if client is None:
        return redirect(url_for("main.connect"))
    dns = request.form.getlist("selected_dn")
    target_ou = request.form.get("target_ou", "").strip()
    if not dns:
        flash("No users selected.", "error")
        return redirect(url_for("main.users"))
    if not target_ou:
        flash("Choose a target OU to move selected users into.", "error")
        return redirect(url_for("main.users"))

    disable_errors = client.bulk_disable_users(dns)
    move_errors = client.bulk_move_objects(dns, target_ou)
    total_errors = set(disable_errors) | set(move_errors)
    if total_errors:
        flash(
            f"Processed {len(dns)} user(s): {len(dns) - len(total_errors)} fully succeeded, "
            f"{len(total_errors)} had at least one failure.",
            "error",
        )
        for dn in total_errors:
            if dn in disable_errors:
                flash(f"Disable failed for {dn}: {disable_errors[dn]}", "error")
            if dn in move_errors:
                flash(f"Move failed for {dn}: {move_errors[dn]}", "error")
    else:
        flash(f"Disabled and moved {len(dns)} user(s) to {target_ou}.", "success")
    return redirect(url_for("main.users"))


# ----------------------------------------------------------------------
# Import users from CSV
# ----------------------------------------------------------------------
@bp.route("/users/import", methods=["GET", "POST"])
def users_import():
    client = _require_client()
    if client is None:
        return redirect(url_for("main.connect"))

    try:
        ous = client.list_ous()
    except ADError as exc:
        flash(str(exc), "error")
        ous = []

    if request.method == "POST":
        stage = request.form.get("stage", "preview")

        if stage == "preview":
            file = request.files.get("csv_file")
            if not file or not file.filename:
                flash("Choose a CSV file to import.", "error")
                return render_template("import_users.html", ous=ous, rows=None)
            content = file.read().decode("utf-8-sig")
            rows = parse_user_import_csv(content)
            session["import_csv_content"] = content
            return render_template(
                "import_users.html",
                ous=ous,
                rows=rows,
                default_ou=request.form.get("default_ou", ""),
            )

        if stage == "commit":
            content = session.pop("import_csv_content", None)
            default_ou = request.form.get("default_ou", "").strip() or None
            if not content:
                flash("Import session expired, please re-upload the CSV.", "error")
                return redirect(url_for("main.users_import"))
            rows = parse_user_import_csv(content)
            created, failed = 0, 0
            for row in rows:
                if row.errors:
                    failed += 1
                    continue
                try:
                    client.create_user(
                        sam_account_name=row.sam_account_name,
                        given_name=row.given_name,
                        surname=row.surname,
                        mail=row.mail,
                        ou_dn=row.ou or default_ou,
                        enabled=row.enabled,
                        password=row.password,
                    )
                    created += 1
                except ADError as exc:
                    failed += 1
                    flash(f"Row {row.line_number} ({row.sam_account_name}): {exc}", "error")
            flash(f"Import finished: {created} created, {failed} failed/skipped.", "success" if failed == 0 else "error")
            return redirect(url_for("main.users"))

    return render_template("import_users.html", ous=ous, rows=None)


# ----------------------------------------------------------------------
# Computers
# ----------------------------------------------------------------------
@bp.route("/computers")
def computers():
    client = _require_client()
    if client is None:
        return redirect(url_for("main.connect"))
    query = request.args.get("q", "").strip()
    try:
        computer_list = client.search_computers(query=query or None)
    except ADError as exc:
        flash(str(exc), "error")
        computer_list = []
    return render_template("computers.html", computers=computer_list, query=query)


@bp.route("/computers/export")
def computers_export():
    client = _require_client()
    if client is None:
        return redirect(url_for("main.connect"))
    try:
        computer_list = client.search_computers()
    except ADError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.computers"))
    csv_data = computers_to_csv(computer_list)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ad_computers.csv"},
    )


# ----------------------------------------------------------------------
# Organizational Units
# ----------------------------------------------------------------------
@bp.route("/ous", methods=["GET", "POST"])
def ous():
    client = _require_client()
    if client is None:
        return redirect(url_for("main.connect"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        parent_dn = request.form.get("parent_dn", "").strip() or client.settings.base_dn
        if not name:
            flash("OU name is required.", "error")
        else:
            try:
                new_dn = client.create_ou(name, parent_dn)
                flash(f"Created OU {new_dn}.", "success")
            except ADError as exc:
                flash(str(exc), "error")
        return redirect(url_for("main.ous"))

    try:
        ou_list = client.list_ous()
    except ADError as exc:
        flash(str(exc), "error")
        ou_list = []
    return render_template("ous.html", ous=ou_list, base_dn=client.settings.base_dn)
