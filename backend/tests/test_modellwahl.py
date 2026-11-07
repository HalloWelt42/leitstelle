"""Das Modell wählt immer die Anwendung (Arbeitslogik 07.11.2026, LS-19): ohne Modell lehnt die Leitstelle ab, ausgewichen
wird nur auf die Alternativen der Anwendung, in ihrer Reihenfolge. Szenarien S80 bis S83 aus docs/SZENARIEN.md."""

from __future__ import annotations

from leitstelle.kern.werte import Auftragszustand as Z, Faehigkeit as F, Massnahmenart as A
from leitstelle.kern.zuteiler import MODELL_FEHLT

from conftest import abschluesse, ausgefuehrt, lade, welt_mit
from test_ende_zu_ende import _warte_bis, aufbau


def test_s80_zuteiler_lehnt_ohne_modell_ab():
    """Eine Anwendung ohne eigene Wahl für die Fähigkeit schickt kein Modell: abgelehnt, nie ein Modell der Leitstelle,
    auch wenn passende geladen und frei sind. Die Rechte gehen vor; auch angehaltener Hintergrund lässt ihn nicht warten."""
    w = welt_mit()
    del w.modellwahl["zusage"][F.TEXT]
    del w.modellwahl["tubevault"][F.TEXT]
    w.verbund.hintergrund_erlaubt = False
    ohne = w.auftrag("zusage", F.TEXT, laufzeit_s=5)
    hintergrund = w.auftrag("tubevault", F.TEXT, laufzeit_s=5)
    ohne_recht = w.auftrag("medienpool", F.TEXT, laufzeit_s=5)
    assert ohne.festes_modell is None
    w.laufen(5)
    v = w.verbund
    for a in (ohne, hintergrund):
        x = v.auftraege[a.kennung]
        assert (x.zustand, x.grund, x.begruendung, x.modell) == (Z.ABGELEHNT, "modell_fehlt", MODELL_FEHLT, None)
    assert v.auftraege[ohne_recht.kennung].grund == "faehigkeit_nicht_erlaubt"
    assert not w.ladevorgaenge


async def test_s81_fassade_ohne_modell_und_mit_alternativen(tmp_path):
    """Die Fassade: ohne `model` 400 `modell_fehlt` mit dem Satz und den Modellen zur Wahl; Namen, die früher die Leitstelle
    wählen ließen, sind unbekannte Modelle; `alternativen` gelten für Text wie für Bilder und gehen nie an den Dienst."""
    async with aufbau(tmp_path) as (c, anw, lage, _):
        r = await anw.post("/chat/completions", json={"messages": [{"role": "user", "content": "hallo"}]})
        fehler = r.json()["error"]
        assert r.status_code == 400 and fehler["code"] == "modell_fehlt" and fehler["message"] == MODELL_FEHLT
        assert "qwen/qwen3-next-80b" in fehler["x-leitstelle"]["modelle"]
        r = await anw.post("/embeddings", json={"input": ["a"]})
        assert r.status_code == 400 and r.json()["error"]["code"] == "modell_fehlt"
        assert r.json()["error"]["x-leitstelle"]["modelle"] == ["text-embedding-bge-m3"]
        for platzhalter in ("auto", "leitstelle", "gross", "schnell"):
            r = await anw.post("/chat/completions", json={"model": platzhalter, "messages": []})
            assert r.status_code == 404 and r.json()["error"]["code"] == "kein_modell" and platzhalter in r.json()["error"]["message"], platzhalter
        r = await anw.post("/chat/completions", json={"alternativen": ["qwen/qwen3-next-80b"], "messages": []})
        assert r.status_code == 400 and r.json()["error"]["code"] == "eingabe"
        r = await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "alternativen": ["gibt-es-nicht"], "messages": []})
        assert r.status_code == 404 and r.json()["error"]["code"] == "kein_modell" and "gibt-es-nicht" in r.json()["error"]["message"]
        r = await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "alternativen": "kein-verzeichnis", "messages": []})
        assert r.status_code == 400 and r.json()["error"]["code"] == "eingabe"

        r = await anw.post("/chat/completions", json={"model": "qwen/qwen3-next-80b", "alternativen": ["zai-org/glm-4.6v-flash"],
                                                      "messages": [{"role": "user", "content": "hallo"}]})
        assert r.status_code == 200, r.text
        assert all("alternativen" not in k for k in lage.anfragen) and lage.anfragen[-1]["model"].startswith("qwen/qwen3-next-80b")
        auftrag = r.headers["x-leitstelle-auftrag"]

        async def fertig() -> bool:
            return (await c.get(f"/api/auftraege/{auftrag}")).json()["zustand"] == "fertig"
        await _warte_bis(fertig)
        e = (await c.get(f"/api/auftraege/{auftrag}")).json()
        assert "Modell qwen/qwen3-next-80b verlangt, sonst zai-org/glm-4.6v-flash" in e["schritte"][0]["text"]


def test_s82_ausweichen_nur_auf_alternativen_der_app():
    """Das kleine Textmodell ist geladen und frei, die App nennt es aber nicht: der Auftrag wartet auf das 80B, die Regel
    weicht nicht dorthin aus (die genannte Alternative ist nicht geladen); er rechnet danach mit dem 80B."""
    w = welt_mit()
    lade(w, "klein@128")
    w.auftrag("zusage", F.TEXT, laufzeit_s=30)
    w.laufen(2)
    z = w.auftrag("zusage", F.TEXT, laufzeit_s=5, festes_modell="qwen-next-80b", alternativen=["qwen-coder-next"])
    w.laufen(20)
    v = w.verbund
    assert v.auftraege[z.kennung].zustand == Z.EINGEREIHT and v.auftraege[z.kennung].wartet_auf_familie == "qwen-next-80b"
    assert not ausgefuehrt(w, A.ALTERNATIVE_AUSWEICHEN)
    assert "keine geladene Alternative" in abschluesse(w, "kette_ausweichen")
    w.laufen_bis_fertig(200)
    assert v.auftraege[z.kennung].zustand == Z.FERTIG and v.modelle[v.auftraege[z.kennung].modell or ""].familie == "qwen-next-80b"
    assert all(a.modell != "klein@128" for a in v.auftraege.values())


def test_s83_ausweichen_in_der_reihenfolge_der_app():
    """Zwei Alternativen geladen und frei: die Regel nimmt die erste der App, nicht die kleinere oder zuerst geladene."""
    w = welt_mit()
    lade(w, "klein@128")
    lade(w, "coder@128")
    w.verbund.knoten["mac-128"].speicher_gb = 200.0            # 80B, Coder und das kleine passen zusammen
    w.auftrag("zusage", F.TEXT, laufzeit_s=60)
    w.laufen(2)
    z = w.auftrag("zusage", F.TEXT, laufzeit_s=5, festes_modell="qwen-next-80b", alternativen=["qwen-coder-next", "qwen-4b"])
    w.laufen(20)
    v = w.verbund
    assert ausgefuehrt(w, A.ALTERNATIVE_AUSWEICHEN)
    assert v.auftraege[z.kennung].modell == "coder@128"
