"""Production mode: the built console is served by the API process, with SPA fallback and no path escape."""
import pytest

from app.config import REPO_DIR

DIST = REPO_DIR / "frontend" / "dist"
pytestmark = pytest.mark.skipif(not (DIST / "index.html").exists(), reason="frontend not built (npx vite build)")


def test_index_and_deep_link_serve_the_app(client):
    for path in ("/", "/contracts/proc-agent-07", "/signal-lab"):
        r = client.get(path)
        assert r.status_code == 200 and "<div id=\"root\">" in r.text


def test_api_routes_are_not_shadowed(client):
    assert client.get("/v1/health").json()["database"] == "ok"
    assert client.get("/v1/does-not-exist").status_code == 404
    assert client.get("/openapi.json").status_code == 200


def test_static_assets_and_no_traversal(client):
    asset = next((DIST / "assets").glob("*.js"))
    assert client.get(f"/assets/{asset.name}").status_code == 200
    r = client.get("/..%2F..%2Fbackend%2Fapp%2Fconfig.py")
    assert "TETHER_DATA_DIR" not in r.text  # falls back to index.html, never serves files outside dist
