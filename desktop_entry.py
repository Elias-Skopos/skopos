"""Frozen Windows entry point; no terminal, one instance per user, private data."""
import argparse
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time


def configure_environment(data_dir=None):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    target = Path(data_dir) if data_dir else Path(os.environ["LOCALAPPDATA"]) / "Skopos" / "Data"
    if not target.is_absolute():
        raise ValueError("A pasta de dados deve ser absoluta.")
    os.environ["SKOPOS_DATA_DIR"] = str(target.resolve())
    os.environ["SKOPOS_POSTGRES_RUNTIME"] = str(root / "postgres/pgsql")
    os.environ["SKOPOS_DESKTOP"] = "1"
    # Frozen paths lack "site-packages", so Streamlit otherwise infers dev mode.
    # Set this before the first Streamlit import in both parent and server child.
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    return root, target


class InstanceLock:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("a+b")
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
    def acquire(self):
        import msvcrt
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    def close(self):
        self.file.close()


def reopen_existing(data_dir):
    from local_config import load_config
    from urllib.request import Request, build_opener, ProxyHandler
    import webbrowser
    path = data_dir / ".runtime/running.json"
    for _ in range(120):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            config = load_config()
            if state["url"] != config.url:
                raise ValueError
            req = Request(f"http://127.0.0.1:{config.port}/_skopos/health", headers={"X-Skopos-Instance":state["token"]})
            with build_opener(ProxyHandler({})).open(req, timeout=1) as response:
                if response.status == 200 and response.read(32).strip() == b"ok":
                    webbrowser.open(config.url, new=0)
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("O Skopos já está iniciando ou a instância existente precisa ser encerrada.")


def run_window(data_dir):
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    from desktop_setup import setup, protect_data_directory
    from local_config import CONFIG_PATH
    from local_paths import APP_ROOT
    import local_postgres
    from local_launcher import launch

    protect_data_directory()
    lock = InstanceLock(data_dir / ".runtime/instance.lock")
    if not lock.acquire():
        lock.close()
        reopen_existing(data_dir)
        return
    events = queue.Queue()
    stop = threading.Event()
    window = tk.Tk()
    window.title("Skopos")
    window.geometry("520x460")
    window.configure(background="#f8f8ff")
    window.resizable(False, False)
    window.iconbitmap(str(APP_ROOT / "assets/skopos_desktop_novo.ico"))
    style = ttk.Style()
    style.configure("TFrame", background="#f8f8ff")
    style.configure("TLabel", background="#f8f8ff", foreground="#171927", font=("Segoe UI", 10))
    frame = ttk.Frame(window, padding=25)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Skopos", font=("Segoe UI", 23, "bold")).pack(anchor="w")
    status = tk.StringVar(value="Preparando sua instalação local...")
    ttk.Label(frame, textvariable=status, wraplength=435).pack(anchor="w", pady=18)
    company = tk.StringVar(value="Minha empresa")
    first = not CONFIG_PATH.exists()
    if first:
        ttk.Label(frame, text="Nome da empresa para o endereço local").pack(anchor="w")
        ttk.Entry(frame, textvariable=company, width=48).pack(fill="x", pady=7)

    def ready(config, token):
        path = data_dir / ".runtime/running.json"
        path.write_text(json.dumps({"url":config.url, "token":token}), encoding="utf-8")
        events.put(("ready", config.url))

    def worker(chosen_name):
        try:
            config = setup(chosen_name)
            launch(config, on_ready=ready, stop_event=stop)
        except Exception as exc:
            # No raw third-party tracebacks containing credentials in UI.
            safe = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "Não foi possível iniciar. Confira os arquivos de diagnóstico da instalação."
            events.put(("error", safe))
        finally:
            events.put(("finished", ""))
    thread = None
    def begin():
        nonlocal thread
        if thread:
            return
        start_button.configure(state="disabled")
        status.set("Preparando banco e acesso. Isso pode levar alguns minutos na primeira abertura.")
        thread = threading.Thread(target=worker, args=(company.get(),), daemon=False)
        thread.start()
    start_button = ttk.Button(frame, text="Preparar e abrir" if first else "Abrir Skopos", command=begin)
    start_button.pack(anchor="w", pady=10)
    def import_google():
        path = filedialog.askopenfilename(title="JSON do cliente Google para computador", filetypes=[("Credenciais JSON", "*.json")])
        if not path:
            return
        try:
            from desktop_google import import_credentials
            import_credentials(path)
            messagebox.showinfo("Google configurado", "Configuração Google salva nesta instalação. Se o aplicativo já estiver aberto, clique em Encerrar Skopos e abra novamente pelo atalho.")
        except ValueError as exc:
            messagebox.showerror("Configuração Google", str(exc))
        except OSError:
            messagebox.showerror("Configuração Google", "Não foi possível salvar o arquivo privado. Confira o acesso à pasta de dados.")
    from desktop_google import BUNDLED_CLIENT_FILE
    google_included = BUNDLED_CLIENT_FILE.is_file()
    google_button = "Alterar configuração Google" if google_included else "Configurar Google: importar JSON"
    google_message = (
        "A configuração Google já está incluída. Você também pode entrar com sua senha local."
        if google_included else
        "Use o JSON do cliente Aplicativo para computador. A senha local funciona sem essa configuração."
    )
    ttk.Button(frame, text=google_button, command=import_google).pack(anchor="w", pady=7)
    ttk.Label(frame, text=google_message, wraplength=450).pack(anchor="w", pady=5)
    def close():
        stop.set()
        status.set("Encerrando o aplicativo com segurança...")
        if thread and thread.is_alive():
            window.after(150, close)
            return
        # This exact data directory belongs to this installed edition.
        if local_postgres.SETTINGS.exists():
            try:
                local_postgres.run_binary("pg_ctl", ["-D", str(local_postgres.DATA), "-m", "fast", "-w", "stop"])
            except Exception:
                pass
        (data_dir / ".runtime/running.json").unlink(missing_ok=True)
        lock.close()
        window.destroy()
    window.protocol("WM_DELETE_WINDOW", close)
    ttk.Button(frame, text="Encerrar Skopos", command=close).pack(anchor="w")
    def poll():
        try:
            while True:
                kind, message = events.get_nowait()
                if kind == "ready":
                    status.set("Aplicativo aberto no navegador:\n"+message+"\n\nMantenha esta janela aberta durante o uso.")
                elif kind == "error":
                    status.set(message)
                    messagebox.showerror("Skopos", message)
        except queue.Empty:
            pass
        window.after(200, poll)
    poll()
    if not first:
        window.after(100, begin)
    window.mainloop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--serve", action="store_true")
    args, rest = parser.parse_known_args()
    root, data_dir = configure_environment(args.data_dir)
    if args.serve:
        from streamlit.web.cli import main as streamlit_main
        sys.argv = ["streamlit", "run", *rest]
        streamlit_main(prog_name="streamlit")
        return
    if args.self_test:
        from desktop_setup import setup
        import local_postgres
        import db
        # The smoke test must use an explicit, newly created target, never user data.
        if not args.data_dir or data_dir.exists():
            raise ValueError("O autoteste exige uma pasta explícita nova e vazia.")
        try:
            setup("Teste de instalação")
            with db.connection() as conn:
                assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0
            from decimal import Decimal
            import home_finance
            assert home_finance.break_even(23000, 35) == Decimal("65714.29")
            from desktop_smoke import verify_server
            checks = verify_server()
            version = json.loads((root / "desktop_defaults.json").read_text(encoding="utf-8"))["version"]
            (data_dir / "self-test-ok.json").write_text(json.dumps({"version":version, "postgres":"ok", "schema":"ok", "home_summary":"ok", **checks, "real_data":False}), encoding="utf-8")
        finally:
            if local_postgres.SETTINGS.exists():
                local_postgres.run_binary("pg_ctl", ["-D", str(local_postgres.DATA), "-m", "fast", "-w", "stop"])
        return
    if args.bootstrap:
        from desktop_setup import setup
        setup()
        return
    run_window(data_dir)


if __name__ == "__main__":
    diagnostic_mode = any(flag in sys.argv for flag in ("--self-test", "--bootstrap", "--serve"))
    try:
        main()
    except Exception as exc:
        if diagnostic_mode:
            raise
        import tkinter.messagebox
        tkinter.messagebox.showerror("Skopos", str(exc) if isinstance(exc, (RuntimeError, ValueError)) else "Não foi possível abrir a instalação local.")
