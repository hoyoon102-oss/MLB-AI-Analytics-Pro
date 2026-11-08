"""Run the Windows launcher headlessly using isolated user data."""
import os
import socket
import subprocess
import tempfile
import time
import requests
from utils.paths import PROJECT_ROOT


def main():
    if os.name != 'nt':
        raise RuntimeError('This check requires Windows cmd.exe')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    with tempfile.TemporaryDirectory() as directory:
        env = dict(os.environ, MLB_ANALYTICS_DATA_DIR=directory,
                   STREAMLIT_SERVER_ADDRESS='127.0.0.1', STREAMLIT_SERVER_PORT=str(port),
                   STREAMLIT_SERVER_HEADLESS='true', STREAMLIT_BROWSER_GATHER_USAGE_STATS='false')
        process = subprocess.Popen(['cmd.exe', '/d', '/c', 'start.bat'], cwd=PROJECT_ROOT,
                                   env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            with requests.Session() as session:
                session.trust_env = False
                for _ in range(80):
                    if process.poll() is not None:
                        raise RuntimeError(process.stdout.read().decode(errors='replace'))
                    try:
                        response = session.get(f'http://127.0.0.1:{port}/_stcore/health', timeout=1)
                        if response.status_code == 200 and response.text == 'ok':
                            print('PASS: start.bat launched Streamlit; health endpoint returned ok')
                            return
                    except requests.RequestException:
                        pass
                    time.sleep(.25)
            raise RuntimeError('Launcher startup timed out')
        finally:
            # Stop only this check's command process and its own server.
            if process.poll() is None:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, check=True)
            process.wait(timeout=10)
            process.stdout.close()


if __name__ == '__main__':
    main()
