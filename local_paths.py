"""Paths shared by the app and local tools; never move an existing database.

The development checkout keeps its current layout. An installed launcher can
set SKOPOS_DATA_DIR and SKOPOS_POSTGRES_RUNTIME to separate private data from
replaceable application binaries.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

APP_ROOT = Path(__file__).resolve().parent


def data_root(environment: Mapping[str, str] | None = None, app_root: Path = APP_ROOT) -> Path:
    environment = os.environ if environment is None else environment
    configured = environment.get("SKOPOS_DATA_DIR", "").strip()
    if not configured:
        return app_root
    destination = Path(configured).expanduser()
    if not destination.is_absolute():
        raise ValueError("SKOPOS_DATA_DIR deve indicar uma pasta absoluta para os dados locais.")
    return destination.resolve()


def postgres_runtime(environment: Mapping[str, str] | None = None,
                     app_root: Path = APP_ROOT) -> Path:
    environment = os.environ if environment is None else environment
    configured = environment.get("SKOPOS_POSTGRES_RUNTIME", "").strip()
    if configured:
        runtime = Path(configured).expanduser()
        if not runtime.is_absolute():
            raise ValueError("SKOPOS_POSTGRES_RUNTIME deve indicar uma pasta absoluta.")
        return runtime.resolve()
    return data_root(environment, app_root) / ".local_postgres" / "runtime" / "pgsql"


DATA_ROOT = data_root()
