"""Development launcher: reload Python, refresh templates, and revalidate assets.

Run ``python dev.py`` or double-click start-dev.bat. Existing application logic,
database configuration, and run.py are shared without being modified.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket

import click
from flask.cli import FlaskGroup
from dotenv import load_dotenv
from sqlalchemy.exc import OperationalError
from werkzeug.serving import is_running_from_reloader

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def create_dev_app(*, validate_schema: bool = True):
    """Use the existing development app with fresh templates and static files."""
    # Import inside Flask's factory so the CLI can recover from a syntax error
    # in application code on the next save instead of losing its watcher.
    from app import create_app
    from run import ensure_runtime_schema

    application = create_app("development")
    application.config.update(
        DEBUG=False,
        TEMPLATES_AUTO_RELOAD=True,
        SEND_FILE_MAX_AGE_DEFAULT=0,
    )
    # The factory registers Jinja filters, so its environment already exists.
    application.jinja_env.auto_reload = True

    if validate_schema:
        click.echo("Checking database schema...")
        try:
            with application.app_context():
                ensure_runtime_schema()
        except OperationalError:
            raise click.ClickException(
                "Cannot validate the database schema. Check the database connection "
                "and DATABASE_URL in .env, then restart the development launcher."
            ) from None
        except RuntimeError as error:
            raise click.ClickException(str(error)) from None
        click.echo("Database schema validated successfully.")
    return application


def _serving_app():
    # The supervisor only watches files. Every child that serves requests must
    # pass the same schema validation as run.py, including after a Python edit.
    return create_dev_app(validate_schema=is_running_from_reloader())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=os.getenv("PORT", "5000"))
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    if not is_running_from_reloader():
        # Windows permits some duplicate binds with SO_REUSEADDR. Check with
        # exclusive access before Werkzeug starts a second watcher/server.
        family = socket.AF_INET6 if ":" in args.host else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                probe.bind((args.host, args.port))
        except OSError as error:
            parser.exit(
                1,
                f"Cannot start on {args.host}:{args.port}: {error.strerror}.\n"
                "If another server is using this port, stop it first or choose --port 5001.\n",
            )
        click.echo("Sta. Clara Norte - development server")
        click.echo("Python edits reload automatically; HTML/CSS/JS edits need browser refresh.")
        click.echo(f"Open http://127.0.0.1:{args.port} - press Ctrl+C to stop.")

    ignored = [
        str(ROOT / directory / "*")
        for directory in (
            ".test-storage", ".venv", "venv", "instance", "tests", "vendor",
            "tools/pdf-runtime", "node_modules",
        )
    ]
    cli = FlaskGroup(create_app=_serving_app, load_dotenv=False, set_debug_flag=False)
    # Flask's CLI keeps the watcher alive if a Python edit introduces an error.
    # Reloading is independent of debug mode; no interactive debugger is enabled.
    cli.main(
        args=[
            "--no-debug", "run", "--reload", "--no-debugger",
            "--host", args.host, "--port", str(args.port),
            "--exclude-patterns", os.pathsep.join(ignored),
        ],
        prog_name="python dev.py",
    )


if __name__ == "__main__":
    main()
