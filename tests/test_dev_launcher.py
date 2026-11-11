"""Exercise development-only settings and a real isolated reload cycle."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from types import ModuleType
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import click
from flask import Flask, current_app
import pytest

import dev


@pytest.fixture
def development_app(monkeypatch):
    application = Flask(__name__)
    application.config.update(SECRET_KEY="launcher-test", DATABASE_SENTINEL="unchanged")
    application.jinja_env.auto_reload = False
    calls = []
    fake_app = ModuleType("app")
    fake_run = ModuleType("run")

    def factory(configuration):
        assert configuration == "development"
        return application

    def validate():
        assert current_app._get_current_object() is application
        calls.append("validated")

    fake_app.create_app = factory
    fake_run.ensure_runtime_schema = validate
    monkeypatch.setitem(sys.modules, "app", fake_app)
    monkeypatch.setitem(sys.modules, "run", fake_run)
    return application, calls, fake_run


def test_only_development_cache_settings_change(development_app):
    application, calls, _ = development_app
    original = dict(application.config)
    assert dev.create_dev_app() is application
    changed = {key for key, value in application.config.items() if original.get(key) != value}
    assert changed == {"TEMPLATES_AUTO_RELOAD", "SEND_FILE_MAX_AGE_DEFAULT"}
    assert not application.debug and application.jinja_env.auto_reload
    assert application.config["DATABASE_SENTINEL"] == "unchanged"
    assert calls == ["validated"]


def test_watcher_skips_validation_but_each_serving_child_checks(development_app, monkeypatch):
    _, calls, _ = development_app
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    dev._serving_app()
    assert calls == []
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    dev._serving_app()
    dev._serving_app()
    assert calls == ["validated", "validated"]


def test_incomplete_schema_blocks_startup(development_app):
    _, _, fake_run = development_app

    def invalid():
        raise RuntimeError("The database schema is incomplete (missing tables: example).")

    fake_run.ensure_runtime_schema = invalid
    with pytest.raises(click.ClickException, match="schema is incomplete"):
        dev.create_dev_app()


def test_database_error_does_not_print_connection_details(development_app):
    from sqlalchemy.exc import OperationalError
    _, _, fake_run = development_app

    def offline():
        raise OperationalError("secret connection text", {}, RuntimeError("private credentials"))

    fake_run.ensure_runtime_schema = offline
    with pytest.raises(click.ClickException) as error:
        dev.create_dev_app()
    assert "Cannot validate" in str(error.value)
    assert "secret connection text" not in str(error.value)
    assert "private credentials" not in str(error.value)


def _get(url, headers=None):
    try:
        response = urlopen(Request(url, headers=headers or {}), timeout=2)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.read().decode(), response.headers


def _wait_until(check, process, log_path, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert process.poll() is None, log_path.read_text(errors="replace")
        try:
            if result := check():
                return result
        except (OSError, URLError):
            pass
        time.sleep(.2)
    pytest.fail("Timed out waiting for development server:\n" + log_path.read_text(errors="replace"))


def _edit(path, content):
    previous = path.stat().st_mtime
    path.write_text(content, encoding="utf-8")
    timestamp = max(time.time(), previous + 2)
    os.utime(path, (timestamp, timestamp))


def _stop(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        # Only this test's spawned process and its reloader child are targeted.
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    process.wait(timeout=10)


def test_live_html_static_python_reload_and_error_recovery(tmp_path):
    """Run the real launcher against disposable code, without a real database."""
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "templates").mkdir()
    (tmp_path / "static").mkdir()
    (tmp_path / "instance").mkdir()
    template = tmp_path / "templates" / "index.html"
    template.write_text("{{ pid }}|{{ version }}|html-v1", encoding="utf-8")
    assets = [tmp_path / "static" / "style.css", tmp_path / "static" / "app.js"]
    for asset in assets:
        asset.write_text("/* asset-v1 */", encoding="utf-8")
    ignored = tmp_path / "instance" / "ignored_sample.py"
    ignored.write_text("VALUE = 1\n", encoding="utf-8")
    sample = tmp_path / "sample_site.py"
    sample_source = '''import os
from flask import Flask, render_template
from instance import ignored_sample
app = Flask(__name__)
@app.get('/')
def index():
    return render_template('index.html', pid=os.getpid(), version='py-v1')
'''
    sample.write_text(sample_source, encoding="utf-8")
    runner = tmp_path / "launch_sample.py"
    runner.write_text(f'''import sys
from pathlib import Path
from types import ModuleType
sys.path.insert(0, {str(root)!r})
import dev
def factory(configuration):
    import sample_site
    return sample_site.app
fake_app = ModuleType('app')
fake_app.create_app = factory
sys.modules['app'] = fake_app
fake_run = ModuleType('run')
fake_run.ensure_runtime_schema = lambda: None
sys.modules['run'] = fake_run
dev.ROOT = Path(__file__).parent
dev.main()
''', encoding="utf-8")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    command = [sys.executable, "-u", str(runner), "--host", "127.0.0.1", "--port", str(port)]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    env.pop("WERKZEUG_RUN_MAIN", None)
    env.pop("WERKZEUG_SERVER_FD", None)
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    log_path = tmp_path / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=tmp_path, env=env, stdout=log, stderr=log, **flags)
        base = f"http://127.0.0.1:{port}"
        try:
            initial = _wait_until(lambda: (r if (r := _get(base))[0] == 200 else None), process, log_path)
            pid = initial[1].split("|")[0]
            assert initial[1].endswith("py-v1|html-v1")
            _edit(template, "{{ pid }}|{{ version }}|html-v2")
            assert _get(base)[1] == f"{pid}|py-v1|html-v2"
            for asset in assets:
                url = base + "/static/" + asset.name
                status, body, headers = _get(url)
                assert status == 200 and "asset-v1" in body
                assert "no-cache" in headers["Cache-Control"]
                assert "max-age=0" in headers["Cache-Control"]
                _edit(asset, "/* asset-v2 */")
                status, body, _ = _get(url, {"If-None-Match": headers["ETag"]})
                assert status == 200 and "asset-v2" in body
            _edit(ignored, "VALUE = 2\n")
            time.sleep(2.5)
            assert _get(base)[1].startswith(pid + "|")
            _edit(sample, sample_source.replace("py-v1", "py-v2"))
            updated = _wait_until(lambda: (r if (r := _get(base))[0] == 200 and "py-v2" in r[1] else None), process, log_path)
            assert updated[1].split("|")[0] != pid
            _edit(sample, "this is invalid python!\n")
            _wait_until(lambda: _get(base)[0] == 500, process, log_path)
            _edit(sample, sample_source.replace("py-v1", "py-v3"))
            _wait_until(lambda: (r if (r := _get(base))[0] == 200 and "py-v3" in r[1] else None), process, log_path)
            second = subprocess.Popen(command, cwd=tmp_path, env=env, stdout=log, stderr=log, **flags)
            try:
                assert second.wait(timeout=10) != 0
            finally:
                _stop(second)
            assert "py-v3" in _get(base)[1]
            assert "Debug mode: off" in log_path.read_text(errors="replace")
        finally:
            _stop(process)
