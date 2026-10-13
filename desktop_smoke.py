"""Exercise the real packaged server, without a browser, using test data only."""
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from urllib.parse import urljoin
from urllib.request import ProxyHandler, build_opener

from local_config import load_config
from local_launcher import preflight, require_free_port, streamlit_command, wait_ready
from local_paths import APP_ROOT, DATA_ROOT


def verify_embedded_window(config):
    """Exercise bundled Python.NET/WebView2 and actual Streamlit rendering."""
    import webview
    result = {}
    window = webview.create_window("Skopos · Autoteste", config.url, hidden=True,
                                   width=1000, height=700)

    def inspect():
        try:
            if not window.events.loaded.wait(30):
                raise RuntimeError("A janela do autoteste não carregou.")
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                text = window.evaluate_js("document.body.innerText")
                if "Faça seu login" in text and "Entrar com senha ou Google" in text:
                    result["webview"] = "ok"
                    result["renderer"] = window.gui.renderer
                    break
                time.sleep(0.25)
            if result.get("webview") != "ok" or result.get("renderer") != "edgechromium":
                raise RuntimeError("O login não foi renderizado na WebView2 do pacote.")
        except Exception:
            result["webview"] = "failed"
        finally:
            window.destroy()

    webview.start(inspect, gui="edgechromium", private_mode=True,
                  storage_path=str(DATA_ROOT / ".webview-test"))
    if result.get("webview") != "ok":
        raise RuntimeError("A janela incorporada falhou no autoteste do pacote.")
    return result


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
            embedded = verify_embedded_window(config)
            return {"server":"ok", "static_assets":"ok", "local_identity":"ok", **embedded}
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
