"""Application source directories must not shadow Python's email package."""
import subprocess
import sys
from pathlib import Path


def test_email_and_flask_import_with_app_directory_on_path():
    root = Path(__file__).resolve().parents[1]
    code = (
        "import sys; sys.path.insert(0, 'app'); "
        "import email.utils, email.message, smtplib, flask; "
        "from app.email_service import send_verification_email; "
        "assert callable(send_verification_email)"
    )
    result = subprocess.run(
        [sys.executable, '-c', code], cwd=root,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_workspace_direct_execution_delegates_to_root_launcher():
    root = Path(__file__).resolve().parents[1]
    code = '''
import runpy
from pathlib import Path
original_run_path = runpy.run_path
def check_launcher(path, *, run_name):
    assert Path(path) == Path.cwd().parent / 'run.py'
    assert run_name == '__main__'
    from app import create_app
    assert callable(create_app)
    print('ROOT_LAUNCHER_OK')
runpy.run_path = check_launcher
original_run_path('workspace.py', run_name='__main__')
'''
    result = subprocess.run(
        [sys.executable, '-c', code], cwd=root / 'app',
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert 'ROOT_LAUNCHER_OK' in result.stdout
