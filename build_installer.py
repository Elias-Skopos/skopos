"""Build a Windows pilot installer from an explicit allowlist, never user data."""
import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from desktop_google import parse_credentials

ROOT = Path(__file__).resolve().parent
POSTGRES_SHA256 = "e2246ba91d22345bc3d017586c09ede52d9df180b1eeb480f050445f1cad84e2"
MODULES = ("app.py", "account_ui.py", "ai_insights.py", "analytics.py", "autonomy.py", "autonomy_ui.py",
           "company_lifecycle.py", "db.py", "horus_api.py", "import_contract.py", "invitation_email.py",
           "local_app_server.py", "local_config.py", "local_identity.py", "local_oidc.py", "local_paths.py",
           "local_postgres.py", "local_launcher.py", "desktop_setup.py", "postgres_backend.py", "ui.py",
           "online_app.py", "welcome_ui.py", "demo_data.py", "demo_ui.py", "migrate_postgres.py",
           "home_finance.py", "home_finance_ui.py", "desktop_smoke.py", "desktop_google.py")
DATA_FILES = (*MODULES, "app_chrome.css", "welcome.css", "desktop_defaults.json", "public_release.json", "TERMS_DESKTOP.txt")


def verify_postgres(runtime, archive):
    if hashlib.file_digest(archive.open("rb"), "sha256").hexdigest() != POSTGRES_SHA256:
        raise ValueError("O arquivo oficial PostgreSQL não corresponde ao checksum validado.")
    with zipfile.ZipFile(archive) as source:
        expected = {n:source.getinfo(n) for n in source.namelist()
                    if n.startswith(("pgsql/bin/", "pgsql/lib/", "pgsql/share/")) and not n.endswith("/")}
        actual = {"pgsql/"+p.relative_to(runtime).as_posix():p for p in runtime.rglob("*") if p.is_file()}
        if set(actual) != set(expected):
            raise ValueError("Os binários PostgreSQL não correspondem ao arquivo oficial.")
        for name, path in actual.items():
            if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(source.read(name)).digest():
                raise ValueError("Um arquivo PostgreSQL foi modificado; compilação cancelada.")


def third_party_notices(archive):
    notices = ["Skopos — avisos das dependências\n", "PostgreSQL: https://www.postgresql.org/about/licence/\n",
               "Inno Setup: https://jrsoftware.org/isinfo.php (avaliar licença comercial antes de comercializar).\n"]
    with zipfile.ZipFile(archive) as source:
        notices.extend(source.read(name).decode("utf-8", errors="replace") for name in
                       ("pgsql/server_license.txt", "pgsql/commandlinetools_3rd_party_licenses.txt"))
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        notices.append(python_license.read_text(encoding="utf-8", errors="replace"))
    for dist in sorted(metadata.distributions(), key=lambda d:d.metadata.get("Name", "")):
        name = dist.metadata.get("Name", "Unknown")
        notices.append(f"\n{name} {dist.version}\n{dist.metadata.get('License-Expression', dist.metadata.get('License', 'Consultar os arquivos abaixo'))}\n")
        for file in dist.files or []:
            if ("dist-info" in str(file) and any(word in file.name.lower() for word in ("license", "copying", "notice"))):
                try:
                    notices.append(Path(dist.locate_file(file)).read_text(encoding="utf-8")+"\n")
                except (OSError, UnicodeError):
                    pass
    target = ROOT / "build/THIRD_PARTY_NOTICES.txt"
    target.write_text("\n".join(notices), encoding="utf-8")
    return target


def audit_bundle(bundle):
    forbidden = {"secrets.toml", "settings.json", "local_app.json", "signing-key.pem", "livraria.db", "teste_Chave_api.py"}
    for file in bundle.rglob("*"):
        if file.is_file() and (file.name in forbidden or file.suffix.lower() in (".db", ".dump")
                              or any(p in (".local_postgres", ".local_auth", "backup_local_postgres", ".test_tmp") for p in file.relative_to(bundle).parts)):
            raise ValueError("O pacote contém um arquivo privado; distribuição cancelada.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inno", type=Path, default=ROOT / ".build_tools/inno/ISCC.exe")
    parser.add_argument("--postgres-runtime", type=Path, default=ROOT / ".local_postgres/runtime/pgsql")
    parser.add_argument("--postgres-archive", type=Path, default=ROOT / ".local_postgres/downloads/postgresql-18.6-5-windows-x64-binaries.zip")
    parser.add_argument("--google-client-json", type=Path,
                        help="JSON do cliente Google Desktop autorizado para inclusão no instalador; nunca cliente web.")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise ValueError("O instalador Windows deve ser compilado no Windows x64.")
    if not args.inno.is_file():
        raise ValueError("Instale o compilador Inno Setup e informe --inno.")
    (ROOT / "build").mkdir(exist_ok=True)
    verify_postgres(args.postgres_runtime, args.postgres_archive)
    defaults = json.loads((ROOT / "desktop_defaults.json").read_text(encoding="utf-8"))
    version = defaults["version"]
    google_seed = None
    if args.google_client_json is not None:
        values = parse_credentials(args.google_client_json, defaults["google_client_id"])
        google_seed = ROOT / "build/google/desktop-client.json"
        google_seed.parent.mkdir(parents=True, exist_ok=True)
        google_seed.write_text(json.dumps({"installed":values}, indent=2), encoding="utf-8")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--windowed", "--noupx", "--name", "Skopos",
               "--distpath", str(ROOT / "dist/runtime"), "--workpath", str(ROOT / "build/pyinstaller"),
               "--specpath", str(ROOT / "build"), "--icon", str(ROOT / "assets/skopos_desktop_novo.ico"),
               "--collect-all", "streamlit", "--collect-all", "plotly", "--collect-all", "authlib",
               "--collect-data", "altair", "--copy-metadata", "Flask", "--hidden-import", "local_oidc",
               "--hidden-import", "psycopg_binary", "--hidden-import", "argon2", "--hidden-import", "PIL.ImageOps"]
    for name in DATA_FILES:
        command.extend(["--add-data", f"{ROOT/name}:."])
    if google_seed is not None:
        command.extend(["--add-data", f"{google_seed}:google"])
    for name in MODULES:
        if name != "app.py":
            command.extend(["--hidden-import", Path(name).stem])
    for name, destination in (("assets", "assets"), (".streamlit/config.toml", ".streamlit")):
        command.extend(["--add-data", f"{ROOT/name}:{destination}"])
    command.extend(["--add-data", f"{args.postgres_runtime}:postgres/pgsql",
                    "--add-data", f"{third_party_notices(args.postgres_archive)}:.", str(ROOT / "desktop_entry.py")])
    with (ROOT / "build/pyinstaller.log").open("w", encoding="utf-8") as log:
        subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    bundle = ROOT / "dist/runtime/Skopos"
    audit_bundle(bundle)
    bundled_google = bundle / "_internal/google/desktop-client.json"
    if google_seed is not None:
        parse_credentials(bundled_google, defaults["google_client_id"])
    elif bundled_google.exists():
        raise ValueError("Há configuração Google sem autorização explícita de inclusão; compilação cancelada.")
    files = [{"path":p.relative_to(bundle).as_posix(), "sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in bundle.rglob("*") if p.is_file()]
    (ROOT / "build/bundle-manifest.json").write_text(json.dumps(files, indent=2), encoding="utf-8")
    output = ROOT / "dist/installer"
    subprocess.run([str(args.inno), f"/DBundleDir={bundle}", f"/DOutputDir={output}", f"/DAppVersion={version}",
                    str(ROOT / "installer/skopos.iss")], cwd=ROOT, check=True)
    installer = output / f"Skopos-Setup-{version}-windows-x64.exe"
    sha = hashlib.sha256(installer.read_bytes()).hexdigest()
    installer.with_suffix(".exe.sha256").write_text(f"{sha}  {installer.name}\n", encoding="utf-8")
    (ROOT / "build/release-candidate.json").write_text(json.dumps({"version":version, "file":installer.name, "sha256":sha,
        "download_url":f"https://github.com/Elias-Skopos/skopos/releases/download/v{version}/{installer.name}", "published":False}, indent=2), encoding="utf-8")
    print(f"Instalador gerado: {installer}")
    print(f"SHA256: {sha}")


if __name__ == "__main__":
    main()
