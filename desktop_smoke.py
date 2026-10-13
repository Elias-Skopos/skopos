"""Exercise the real packaged server, without a browser, using test data only."""
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
from urllib.parse import urljoin
from urllib.request import ProxyHandler, build_opener

from local_config import load_config
from local_launcher import preflight, require_free_port, streamlit_command, wait_ready
from local_paths import APP_ROOT, DATA_ROOT


def verify_server():
    # Called only after the self-test's fresh-directory and empty-company checks.
    config = load_config()
    preflight(config)
    require_free_port(config.port)
    token = secrets.token_urlsafe(32)
    environment = {**os.environ, "SKOPOS_INSTANCE_TOKEN": token,
                   "STREAMLIT_GLOBAL_DEVELOPMENT_MODE": "false"}
    process = None
    log_path = DATA_ROOT / ".local_postgres/self-test-server.log"
    base = f"http://127.0.0.1:{config.port}/"
    opener = build_opener(ProxyHandler({}))
    try:
        with log_path.open("ab") as log:
            process = subprocess.Popen(streamlit_command(config), cwd=APP_ROOT,
                                       env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            wait_ready(process, config.port, token, timeout=45)
            with opener.open(base, timeout=10) as response:
                html = response.read().decode("utf-8")
                assert response.status == 200
            scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
            assert scripts, "A página não contém o JavaScript do aplicativo."
            script_url = urljoin(base, scripts[0])
            assert script_url.startswith(base), "O JavaScript não está no servidor local."
            with opener.open(script_url, timeout=10) as response:
                assert response.status == 200 and response.read(128)
                assert "javascript" in response.headers.get("Content-Type", "")
            with opener.open(base+"identity/.well-known/openid-configuration", timeout=10) as response:
                metadata = json.load(response)
                assert metadata["issuer"] == config.url+"/identity"
            with opener.open(metadata["jwks_uri"], timeout=10) as response:
                assert json.load(response)["keys"]
            return {"server":"ok", "static_assets":"ok", "local_identity":"ok"}
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
