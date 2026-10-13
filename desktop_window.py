"""One native WebView2 window owns the local server and its lifetime."""
from html import escape
import json
from pathlib import Path
import threading
from urllib.parse import urlparse
import webbrowser


def startup_html(first: bool, error: str = "") -> str:
    company = ('<label for="company">Nome da empresa</label>'
               '<input id="company" value="Minha empresa" maxlength="120" required>') if first else ''
    message = escape(error) if error else "Preparando seu espaço de trabalho…"
    return f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>*{{box-sizing:border-box}}body{{margin:0;background:#f8f8ff;color:#171927;
    font:16px 'Segoe UI',sans-serif;display:grid;place-items:center;min-height:100vh}}
    main{{width:min(460px,90vw)}}h1{{font-size:42px;color:#514ed5;margin-bottom:12px}}
    p{{line-height:1.6}}label{{display:block;margin-top:24px}}input{{width:100%;padding:14px;
    border:1px solid #cbd0e6;border-radius:10px;font:inherit;margin-top:8px}}
    button{{background:#625fe9;color:white;border:0;border-radius:10px;padding:14px 22px;
    font:inherit;cursor:pointer;margin-top:20px}}button:disabled{{opacity:.6;cursor:wait}}</style>
    <main><h1>Skopos</h1><p id="status" role="status">{message}</p>
    {company if not error else ''}
    {'<button id="start" onclick="begin()">Preparar e abrir</button>' if first and not error else ''}
    <p>Seus dados ficam neste computador.</p></main>
    <script>async function begin(){{const b=document.getElementById('start');if(b)b.disabled=true;
    document.getElementById('status').textContent='Preparando banco e acesso. Aguarde…';
    await window.pywebview.api.begin(document.getElementById('company')?.value || 'Minha empresa');}}
    window.addEventListener('pywebviewready',()=>{{if({json.dumps(not first and not error)})begin();}});
    </script></html>'''


class DesktopAPI:
    def __init__(self, data_dir, stop):
        self._data_dir = Path(data_dir)
        self._stop = stop
        self._window = None
        self._thread = None
        self._mutex = threading.Lock()
        self._home = None

    def begin(self, company="Minha empresa"):
        # Installation preparation is available only on the built-in HTML page.
        if self._window.get_current_url() is not None or self._stop.is_set():
            return False
        with self._mutex:
            if self._thread is not None:
                return False
            self._thread = threading.Thread(target=self._run, args=(str(company)[:120],), daemon=False)
            self._thread.start()
        return True

    def open_google(self, url):
        current = urlparse(self._window.get_current_url() or "")
        home = urlparse(self._home or "")
        destination = urlparse(url)
        if (not self._home or (current.scheme, current.netloc) != (home.scheme, home.netloc)
                or current.path != "/identity/google/start"
                or destination.scheme != "https" or destination.netloc != "accounts.google.com"
                or destination.path != "/o/oauth2/v2/auth"):
            return False
        return webbrowser.open(url, new=0)

    def _ready(self, config, token):
        if self._stop.is_set():
            return
        state = self._data_dir / ".runtime/running.json"
        state.write_text(json.dumps({"url": config.url, "token": token}), encoding="utf-8")
        self._home = config.url
        self._window.load_url(config.url)

    def _run(self, company):
        from desktop_setup import setup
        from local_launcher import launch
        try:
            config = setup(company)
            if not self._stop.is_set():
                result = launch(config, on_ready=self._ready, stop_event=self._stop, open_browser=False)
                if not self._stop.is_set():
                    raise RuntimeError("O aplicativo encerrou inesperadamente. Feche e abra o Skopos novamente.")
        except Exception as exc:
            safe = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "Não foi possível iniciar. Confira os arquivos de diagnóstico da instalação."
            if not self._stop.is_set():
                self._window.load_html(startup_html(False, safe))


def run_desktop(data_dir):
    import webview
    from webview.menu import Menu, MenuAction
    from local_config import CONFIG_PATH
    from local_paths import APP_ROOT
    import local_postgres

    # Refuse the obsolete IE fallback if WebView2 is missing. Streamlit needs
    # Chromium; opening a blank legacy window would conceal the real problem.
    import winreg
    runtime_key = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    available = False
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, runtime_key, 0, winreg.KEY_READ | view) as key:
                    version, _ = winreg.QueryValueEx(key, "pv")
                    available = available or bool(version and version != "0.0.0.0")
            except OSError:
                pass
    if not available:
        raise RuntimeError("Instale o Microsoft Edge WebView2 Runtime para abrir o Skopos: https://developer.microsoft.com/microsoft-edge/webview2/")

    stop = threading.Event()
    api = DesktopAPI(data_dir, stop)
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["ALLOW_FILE_URLS"] = False
    window = webview.create_window("Skopos", html=startup_html(not CONFIG_PATH.exists()),
                                   js_api=api, width=1280, height=820, min_size=(800, 600),
                                   background_color="#f8f8ff", text_select=True)
    api._window = window
    window.events.closed += stop.set

    def import_google():
        from desktop_google import import_credentials
        selection = window.create_file_dialog(webview.FileDialog.OPEN, file_types=("Credenciais JSON (*.json)",))
        if selection:
            try:
                import_credentials(selection[0])
                window.create_confirmation_dialog("Google configurado", "Configuração salva. Feche e abra o Skopos para usá-la.")
            except (ValueError, OSError):
                window.create_confirmation_dialog("Configuração Google", "Não foi possível importar. Escolha o JSON do cliente Google para computador configurado para o Skopos.")

    def activation_loop():
        signal = Path(data_dir) / ".runtime/activate"
        while not stop.wait(0.25):
            if signal.exists():
                signal.unlink(missing_ok=True)
                window.restore()
                window.show()

    try:
        webview.start(activation_loop, gui="edgechromium", private_mode=False,
                      storage_path=str(Path(data_dir) / ".webview"),
                      user_agent="Mozilla/5.0 SkoposDesktop/1.0", icon=str(APP_ROOT / "assets/skopos_desktop_novo.ico"),
                      menu=[Menu("Skopos", [MenuAction("Configurar Google…", import_google),
                                            MenuAction("Encerrar", window.destroy)])])
    finally:
        stop.set()
        if api._thread is not None:
            api._thread.join()
        if local_postgres.SETTINGS.exists():
            try:
                local_postgres.run_binary("pg_ctl", ["-D", str(local_postgres.DATA), "-m", "fast", "-w", "stop"])
            except (RuntimeError, OSError):
                pass
