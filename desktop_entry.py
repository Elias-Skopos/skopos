"""Frozen Windows entry point; no terminal, one instance per user, private data."""
import argparse
import json
import os
from pathlib import Path
import sys
import time


def configure_environment(data_dir=None):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    target = Path(data_dir) if data_dir else Path(os.environ["LOCALAPPDATA"]) / "Skopos" / "Data"
    if not target.is_absolute():
        raise ValueError("A pasta de dados deve ser absoluta.")
    os.environ["SKOPOS_DATA_DIR"] = str(target.resolve())
    os.environ["SKOPOS_POSTGRES_RUNTIME"] = str(root / "postgres/pgsql" if getattr(sys, "frozen", False) else root / ".local_postgres/runtime/pgsql")
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
                    (data_dir / ".runtime/activate").touch()
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("O Skopos já está iniciando ou a instância existente precisa ser encerrada.")


def run_window(data_dir):
    from desktop_setup import protect_data_directory
    from desktop_window import run_desktop

    protect_data_directory()
    lock = InstanceLock(data_dir / ".runtime/instance.lock")
    if not lock.acquire():
        lock.close()
        reopen_existing(data_dir)
        return
    try:
        run_desktop(data_dir)
    finally:
        (data_dir / ".runtime/running.json").unlink(missing_ok=True)
        lock.close()


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
