"""Export only public Skopos source files for manual GitHub publication."""
import hashlib
import json
from pathlib import Path
import zipfile

from build_installer import DATA_FILES

ROOT = Path(__file__).resolve().parent
EXTRA_FILES = (
    "desktop_entry.py", "build_installer.py", "export_sources.py", ".gitignore",
    "requirements.txt", "requirements-desktop.lock", "README.md", "PUBLICACAO_WINDOWS.md", "ATUALIZACAO_0_1_4.md", "ATUALIZACAO_0_1_5.md", "ATUALIZACAO_0_1_6.md",
    "POSTGRESQL.md", "POSTGRESQL_LOCAL.md", "BACKLOG_INSTALAVEL.md",
    "local_app.json.example", ".streamlit/config.toml", ".streamlit/secrets.toml.example",
    "installer/skopos.iss", "Iniciar Skopos local.cmd", "Fazer backup local.cmd",
    "assets/skopos_desktop_novo.ico", "assets/logo_novo.png", "assets/logo_login.svg",
    "assets/logo_login.png", "assets/logo_barra_lateral.svg", "assets/logo_barra_lateral_dark.svg", "assets/Logo_barra_lateral.png",
    "assets/logo.ico", "assets/login_illustration.svg",
)


def main():
    version = json.loads((ROOT / "desktop_defaults.json").read_text(encoding="utf-8"))["version"]
    names = sorted(set(DATA_FILES + EXTRA_FILES) | {p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_*.py")})
    files = []
    for name in names:
        path = ROOT / name
        if not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise ValueError(f"Arquivo ausente ou fora do projeto: {name}")
        files.append((name, path))
    output = ROOT / "dist/installer"
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"Skopos-Codigo-{version}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in files:
            archive.write(path, name)
        archive.writestr("ARQUIVOS_PUBLICOS.json", json.dumps([
            {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for name, path in files
        ], ensure_ascii=False, indent=2))
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError("O pacote de código falhou na verificação de integridade.")
    checksum = hashlib.file_digest(target.open("rb"), "sha256").hexdigest()
    target.with_suffix(".zip.sha256").write_text(f"{checksum}  {target.name}\n", encoding="utf-8")
    print(f"Pacote público: {target} ({len(files)} arquivos)")


if __name__ == "__main__":
    main()
