"""Start an isolated headless server, check health, then stop our own process."""
import subprocess
import sys
import time

import requests


def main():
    process = subprocess.Popen([
        sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless=true",
        "--server.address=127.0.0.1", "--server.port=18504", "--browser.gatherUsageStats=false",
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    try:
        with requests.Session() as session:
            session.trust_env = False
            for _ in range(40):
                if process.poll() is not None:
                    raise RuntimeError(process.stdout.read())
                try:
                    response = session.get("http://127.0.0.1:18504/_stcore/health", timeout=1)
                    if response.status_code == 200 and response.text == "ok":
                        print("PASS: Streamlit started successfully; health endpoint returned ok", flush=True)
                        return
                except requests.RequestException:
                    pass
                time.sleep(.25)
        raise RuntimeError("Streamlit startup timed out")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()


if __name__ == "__main__":
    main()
