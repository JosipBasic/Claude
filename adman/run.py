import os
import sys

from app import create_app

app = create_app()


def main() -> None:
    host = os.environ.get("ADMAN_HOST", "127.0.0.1")
    port = int(os.environ.get("ADMAN_PORT", "5000"))

    # Frozen (PyInstaller) builds have no reloader/debugger available and are
    # meant to be run as a standalone server, so serve them with waitress
    # instead of Flask's development server.
    if getattr(sys, "frozen", False):
        from waitress import serve

        serve(app, host=host, port=port)
    else:
        app.run(debug=True, host=host, port=port)


if __name__ == "__main__":
    main()
