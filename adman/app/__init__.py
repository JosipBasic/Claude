from __future__ import annotations

import os

from flask import Flask


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-key-change-me"),
    )
    if test_config:
        app.config.update(test_config)

    from . import routes

    app.register_blueprint(routes.bp)

    return app
