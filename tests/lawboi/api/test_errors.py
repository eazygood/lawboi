from fastapi import FastAPI
from fastapi.testclient import TestClient
from lawboi.api.errors import register_exception_handlers
from lawboi.domain.errors import NoSourcesFoundError, UnsupportedModelError


def _app():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom-422")
    def boom_422():
        raise NoSourcesFoundError("none")

    @app.get("/boom-400")
    def boom_400():
        raise UnsupportedModelError("gpt-5")

    return TestClient(app)


def test_no_sources_maps_to_422():
    assert _app().get("/boom-422").status_code == 422


def test_unsupported_model_maps_to_400():
    r = _app().get("/boom-400")
    assert r.status_code == 400
    assert "gpt-5" in r.json()["detail"]
