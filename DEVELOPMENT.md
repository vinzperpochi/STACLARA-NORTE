# Development launcher

Double-click **start-dev.bat** in this folder once per work session. Keep its
window open, then use the existing browser tab at http://127.0.0.1:5000.
The launcher uses this project's `.venv` if present, or `python` from PATH.
It uses the same installed dependencies and `.env` as `run.py`.

From PowerShell, the equivalent is:

```powershell
python dev.py
```

- **HTML:** refresh the browser; Jinja loads the saved template automatically.
- **CSS / JavaScript:** refresh the browser; assets are revalidated instead of
  being kept fresh in the browser cache.
- **Python:** the server restarts automatically. Wait for the startup/database
  check to finish before submitting a form or scanning an RFID card.
- **.env, dependencies, or database schema changes:** stop with Ctrl+C and start
  again. Apply migrations explicitly when needed, as with the existing launcher.
- **Finished working:** press Ctrl+C, then close the window.

The existing `run.py`, production entry point, application routes, permissions,
RFID logic, and database settings are unchanged. The new launcher selects the
existing development configuration, enables template refresh, and revalidates
static files. It uses Flask's built-in Python reloader with the interactive
debugger disabled. It does not create tables, migrate, seed, or erase records.
The original schema validation runs before each serving process starts. Logs,
uploads, test output, and bundled dependencies are excluded from the watcher.

`HOST` and `PORT` keep their existing defaults (`0.0.0.0` and `5000`), including
LAN access for the reader. Command-line overrides are available:

```powershell
python dev.py --host 127.0.0.1 --port 5001
```

Run one server on a given port. If another `run.py` or `dev.py` server is already
running, stop it with Ctrl+C first. The launcher does not stop other processes.
Browser refresh is manual; the launcher does not add automatic browser refresh.
The development server is for local development; use the existing production
entry point for deployment.
