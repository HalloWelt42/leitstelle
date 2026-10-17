"""Auslieferung der gebauten Oberfläche: Symbole und Manifest mit passendem Typ, für GET und HEAD."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from leitstelle.api.app import erstellen
from leitstelle.konfig import Konfig

TYPEN = {
    "favicon.ico": {"image/x-icon", "image/vnd.microsoft.icon"},
    "favicon.svg": {"image/svg+xml"},
    "apple-touch-icon.png": {"image/png"},
    "icon-192.png": {"image/png"},
    "site.webmanifest": {"application/manifest+json"},
}


def _client(tmp_path: Path) -> httpx.AsyncClient:
    wurzel = tmp_path / "oberflaeche"
    wurzel.mkdir()
    (wurzel / "index.html").write_text("<!doctype html>")
    for name in TYPEN:
        (wurzel / name).write_bytes(b"x")
    app = erstellen(Konfig(daten=tmp_path / "daten", oberflaeche=wurzel), mit_takt=False)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1")


@pytest.mark.parametrize("methode", ["GET", "HEAD"])
async def test_symbole_und_manifest_mit_typ(tmp_path: Path, methode: str):
    async with _client(tmp_path) as c:
        for name, typen in TYPEN.items():
            antwort = await c.request(methode, f"/{name}")
            assert antwort.status_code == 200, name
            assert antwort.headers["content-type"].split(";")[0] in typen, name


async def test_unbekannter_pfad_bekommt_die_seite(tmp_path: Path):
    async with _client(tmp_path) as c:
        antwort = await c.head("/knoten/mac")
        assert antwort.status_code == 200
        assert antwort.headers["content-type"].startswith("text/html")
