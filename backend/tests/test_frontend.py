"""The built browser app served at / (app.py _serve_frontend, feat/render-deploy).

Each test builds a tiny stand-in for frontend/dist in a temporary folder:
index.html, one asset, and a file OUTSIDE the folder that must never be sent.
"""

import pytest
from fastapi.testclient import TestClient

from vaani import __version__
from vaani.app import create_app
from vaani.config import FrontendSettings, Settings

INDEX = "<html>vaani app</html>"


@pytest.fixture
def dist(tmp_path):
    folder = tmp_path / "dist"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text(INDEX, encoding="utf-8")
    (folder / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("not for the browser", encoding="utf-8")
    return folder


def client_for(folder) -> TestClient:
    # An absolute dist_dir: app.py joins it to backend/, and an absolute path
    # replaces the base.
    settings = Settings(frontend=FrontendSettings(dist_dir=str(folder)))
    return TestClient(create_app(settings))


def test_root_serves_index_html(dist) -> None:
    response = client_for(dist).get("/")

    assert response.status_code == 200
    assert response.text == INDEX
    assert response.headers["content-type"].startswith("text/html")


def test_an_existing_file_is_sent_as_is(dist) -> None:
    response = client_for(dist).get("/assets/app.js")

    assert response.status_code == 200
    assert response.text == "console.log(1)"


def test_a_browser_route_gets_index_html(dist) -> None:
    """/talk is drawn by react-router in the browser; the server only has to
    send the one HTML page."""
    response = client_for(dist).get("/talk/settings")

    assert response.status_code == 200
    assert response.text == INDEX


@pytest.mark.parametrize("path", ["/auth/nope", "/ws/nope", "/health/extra"])
def test_unknown_api_paths_stay_404(dist, path) -> None:
    assert client_for(dist).get(path).status_code == 404


def test_api_routes_still_win(dist) -> None:
    client = client_for(dist)

    assert client.get("/health").json() == {"status": "ok", "version": __version__}
    # Auth is off in tests: /auth/me answers its own JSON, not the page.
    assert client.get("/auth/me").json() == {"email": None, "name": None}


def test_a_path_cannot_climb_out_of_dist(dist) -> None:
    response = client_for(dist).get("/%2e%2e/outside.txt")

    assert "not for the browser" not in response.text


def test_no_dist_folder_means_no_frontend(tmp_path) -> None:
    client = client_for(tmp_path / "missing")

    assert client.get("/").status_code == 404
    assert client.get("/health").status_code == 200
