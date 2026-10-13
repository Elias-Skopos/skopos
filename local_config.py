"""Public configuration for the single-computer edition (no DNS/hosts edits)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import unicodedata

from local_paths import DATA_ROOT

CONFIG_PATH = DATA_ROOT / "local_app.json"


def company_hostname(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    if not slug or len(slug) > 63:
        raise ValueError("Informe um nome que resulte em 1 a 63 letras, números ou hífens.")
    return f"skopos.{slug}.localhost"


@dataclass(frozen=True)
class LocalConfig:
    # Preserve existing Google OAuth configuration until a name is chosen.
    hostname: str = "localhost"
    port: int = 8501

    def __post_init__(self) -> None:
        if not isinstance(self.hostname, str):
            raise ValueError("O nome local deve ser um texto.")
        labels = self.hostname.split(".")
        if (len(self.hostname) > 253 or labels[-1] != "localhost"
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)):
            raise ValueError("Use localhost ou um nome local como skopos.empresa.localhost, sem protocolo ou porta.")
        if type(self.port) is not int or not 1024 <= self.port <= 65535:
            raise ValueError("A porta do aplicativo deve ser um número inteiro entre 1024 e 65535.")

    @property
    def url(self) -> str:
        return f"http://{self.hostname}:{self.port}"


def load_config(path: Path = CONFIG_PATH) -> LocalConfig:
    if not path.is_file():
        return LocalConfig()
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(values, dict) or set(values) != {"hostname", "port"}:
            raise ValueError
        return LocalConfig(**values)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("A configuração local é inválida. Confira local_app.json ou use configure novamente.") from exc


def save_config(config: LocalConfig, path: Path = CONFIG_PATH) -> None:
    temporary = path.with_suffix(path.suffix + ".new")
    try:
        temporary.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
