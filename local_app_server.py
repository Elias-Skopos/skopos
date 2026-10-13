"""Streamlit entry point with readiness specific to the launching process."""
import hmac
import os
import logging
from contextlib import asynccontextmanager

import streamlit as st
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.routing import Mount
from starlette.middleware.wsgi import WSGIMiddleware

from local_paths import APP_ROOT


class PrivateAccessLog(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5 and isinstance(record.args[2], str):
            args = list(record.args)
            args[2] = args[2].split("?", 1)[0]
            record.args = tuple(args)
        return True


@asynccontextmanager
async def private_access_logs(app):
    access = logging.getLogger("uvicorn.access")
    privacy = PrivateAccessLog()
    access.addFilter(privacy)
    try:
        yield
    finally:
        access.removeFilter(privacy)


async def readiness(request):
    expected = os.environ.get("SKOPOS_INSTANCE_TOKEN", "")
    supplied = request.headers.get("X-Skopos-Instance", "")
    if not expected or not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        return PlainTextResponse("unavailable", status_code=404)
    return PlainTextResponse("ok")


routes = [Route("/_skopos/health", readiness)]
if os.environ.get("SKOPOS_DESKTOP") == "1":
    from desktop_setup import auth_settings, KEY_PATH
    from local_oidc import create_provider
    import db
    import local_postgres
    db.configure_database(local_postgres.database_url(local_postgres.read_settings()))
    routes.append(Mount("/identity", WSGIMiddleware(create_provider(auth_settings(), KEY_PATH))))
app = st.App(APP_ROOT / "app.py", routes=routes, lifespan=private_access_logs)
