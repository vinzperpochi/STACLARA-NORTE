"""Start the app through the same factory used by the WSGI deployment."""
from __future__ import annotations

import os
import sys
import time

from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from app import create_app
from app.extensions import db
def ensure_runtime_schema() -> None:
    """Validate manually provisioned tables; never create or alter schema."""
    inspector = inspect(db.engine)
    missing_tables = sorted(set(db.metadata.tables) - set(inspector.get_table_names()))
    missing_columns = []
    for table in db.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        missing_columns.extend(
            f"{table.name}.{column.name}"
            for column in table.columns
            if column.name not in existing
        )
    if missing_tables or missing_columns:
        problems = []
        if missing_tables:
            problems.append("missing tables: " + ", ".join(missing_tables))
        if missing_columns:
            problems.append("missing columns: " + ", ".join(missing_columns))
        raise RuntimeError(
            "The database schema is incomplete (" + "; ".join(problems) + "). "
            "Ensure DATABASE_URL points to your Supabase PostgreSQL database. "
            "See README_REVISED.md for setup instructions. Run 'flask db upgrade heads' to apply migrations."
        )


def main() -> None:
    print("Initializing application...")
    app = create_app(os.getenv("FLASK_CONFIG", "development"))
    print("Checking database schema...")
    try:
        # Managed database poolers can occasionally close a connection while
        # waking up or recycling an idle connection. Retrying only this
        # read-only schema validation keeps normal startup reliable without
        # changing application data or database schema.
        attempts = 3
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                with app.app_context():
                    ensure_runtime_schema()
                print("Database schema validated successfully!")
                last_error = None
                break
            except OperationalError as error:
                last_error = error
                if attempt == attempts:
                    raise
                print(f"Database connection attempt {attempt}/{attempts} failed; retrying in 2 seconds...")
                time.sleep(2)
        if last_error is not None:
            raise last_error
    except OperationalError as error:
        driver_error = getattr(error, "orig", error)
        error_text = str(driver_error).lower()
        
        if "database" in error_text and "does not exist" in error_text:
            message = (
                "Hindi makita ang Supabase database. Ensure DATABASE_URL is set correctly in .env. "
                "See README_REVISED.md for connection setup instructions."
            )
        elif "password authentication failed" in error_text or "access denied" in error_text:
            message = (
                "Hindi tinanggap ang database credentials. Suriin ang DATABASE_URL "
                "sa .env at tiyaking tama ang password."
            )
        elif ("could not connect" in error_text or "connection refused" in error_text
              or "server closed the connection unexpectedly" in error_text
              or "getaddrinfo failed" in error_text):
            message = (
                "Hindi makakonekta sa Supabase pagkatapos ng retry. Suriin ang internet/DNS connection "
                "at subukang muli pagkalipas ng ilang minuto."
            )
        else:
            message = f"Database connection/schema check failed: {driver_error}"
        print(f"Database startup error: {message}", file=sys.stderr)
        raise SystemExit(1) from None
    except RuntimeError as error:
        print(f"Database schema error: {error}", file=sys.stderr)
        raise SystemExit(1) from None

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    print(f"Starting server on {host}:{port}...")
    print(f"Open your browser to: http://127.0.0.1:{port}")
    print("Press CTRL+C to stop the server")
    print()
    app.logger.info("Starting Barangay Records Management System on %s:%s", host, port)
    app.run(host=host, port=port, debug=app.config.get("DEBUG", False))


if __name__ == "__main__":
    main()
