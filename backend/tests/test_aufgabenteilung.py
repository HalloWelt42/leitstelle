"""Verbindliche Rollen: vollständiger Katalog, Modellwahl der App, sichere Reservierung und passende Auskunft."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from leitstelle.fach.auskunft import einschaetzung
from leitstelle.kern.messungen import Messwerk
from leitstelle.kern.modelle import Auftrag
from leitstelle.kern.regeln.bausteine import Kontext, anwendung_darf_extern, extern_dienst_vorhanden
from leitstelle.kern.speicherplaner import planen
from leitstelle.kern.werte import Auftragszustand as Z, Dienstzustand as D, Faehigkeit as F, Modellzustand as M, Prioritaet as P
from leitstelle.protokoll.fassade import Einschaetzungsanfrage

from conftest import welt_mit
from test_schlaf import MODELL, aufbau


def test_externe_erlaubnis_ist_keine_modellwahl():
    w = welt_mit()
    a = w.auftrag('fundus', F.TEXT, festes_modell='qwen-next-80b', alternativen=[], extern=['qwen-35b-extern'])
    k = Kontext(w.verbund, w.messwerk, auftrag=a)
    assert not w.verbund.extern_erlaubt(a, w.verbund.modelle['qwen35@extern'])
    assert not anwendung_darf_extern(k)
    assert not extern_dienst_vorhanden(k)
    assert k.modell_ziel is None
    a.alternativen = ['qwen-35b-extern']
    a.extern_familien = []
    assert anwendung_darf_extern(k)
    assert extern_dienst_vorhanden(k) and k.modell_ziel == 'qwen35@extern'


def test_ist_verbrauch_ist_untergrenze_der_reservierung():
    w = welt_mit()
    v = w.verbund
    vorher = v.frei_gb('mac-128')
    m = v.modelle['qwen80@128']
    m.gb_jetzt = m.gb + 20
    assert v.frei_gb('mac-128') == pytest.approx(vorher - 20)
    assert m.speicherbedarf_gb == pytest.approx(m.gb_jetzt)
    m.gb_jetzt = 0.5
    assert v.frei_gb('mac-128') == vorher


def test_freigabe_mehrerer_modelle_nach_restzeit():
    w = welt_mit()
    v = w.verbund
    for m in v.modelle.values():
        m.zustand = M.FREI
    v.knoten['mac-128'].budget_fest_gb = 18
    for i, (kennung, gb) in enumerate([('qwen80@128', 10), ('coder@128', 8)]):
        m = v.modelle[kennung]
        m.gb, m.zustand = gb, M.RECHNET
        a = Auftrag(kennung=f'besetzt-{i}', anwendung='fundus' if i == 0 else 'codehilfe', faehigkeit=F.TEXT,
                    eingang_s=0, prioritaet=P.NORMAL, zustand=Z.LAEUFT, modell=kennung, dienst=m.dienst, knoten='mac-128')
        v.auftraege[a.kennung] = a
    messwerk = Messwerk()
    messwerk.merke_laufzeit('fundus', 'text', 60)
    messwerk.merke_laufzeit('codehilfe', 'text', 5)
    p = planen(v, 'mac-128', 15, messwerk)
    assert not p.passt and p.frei_nach_s == 60
    assert p.blockiert_durch == ['coder@128', 'qwen80@128']
    p = planen(v, 'mac-128', 8, messwerk)
    assert p.frei_nach_s == 5 and p.blockiert_durch == ['coder@128']


def test_einschaetzung_verwendet_rechnerwunsch_und_prioritaet():
    w = welt_mit(ruhe_faehigkeiten=[])
    v = w.verbund
    v.dienste['laeufer-32'].zustand = D.BEREIT
    v.modelle['klein@128'].zustand = v.modelle['klein@32'].zustand = M.GELADEN
    b = SimpleNamespace(verbund=v, messwerk=w.messwerk)
    anfrage = Einschaetzungsanfrage(model='qwen-4b')
    vorher = len(v.auftraege)
    e = einschaetzung(b, 'kiste', anfrage, F.TEXT, 'qwen-4b', [], prioritaet=P.NORMAL, rechner=['mac-32'])
    assert e.sofort and e.rechner == 'MacBook'
    assert len(v.auftraege) == vorher
    v.hintergrund_erlaubt = False
    e = einschaetzung(b, 'kiste', anfrage, F.TEXT, 'qwen-4b', [], prioritaet=P.HINTERGRUND)
    assert not e.sofort and 'Hintergrund' in e.grund


async def test_jede_app_sieht_alle_modelle_ohne_aufrufrechte_oder_laden(tmp_path):
    async with aufbau(tmp_path, mit_takt=False) as a:
        v = a.app.state.betrieb.verbund
        for m in v.modelle.values():
            m.zustand = M.FREI
        r = await a.c.post('/api/anwendungen', json={'name': 'Katalogleser', 'faehigkeiten': ['einbettung']})
        assert r.status_code == 200
        async with httpx.AsyncClient(base_url=a.url, headers={'Authorization': 'Bearer ' + r.json()['schluessel']}) as c:
            vorher = list(a.agent.befehle)
            modelle = (await c.get('/v1/models')).json()['data']
            xs = {x['id']: x['x-leitstelle'] for x in modelle}
            assert MODELL in xs and 'text' in xs[MODELL]['faehigkeiten']
            assert not xs[MODELL]['aufruf_erlaubt']
            assert not xs[MODELL]['geladen']
            assert any(o['quelle'] == 'modell_laeufer' for o in xs[MODELL]['orte'])
            assert 'probe' in xs and any(o['quelle'] == 'eigener_dienst' for o in xs['probe']['orte'])
            assert not xs['probe']['aufruf_erlaubt']
            dienst = next(x for x in (await c.get('/v1/dienste')).json()['data'] if x['kennung'] == 'probe')
            assert dienst['faehigkeiten'] and not dienst['aufruf_erlaubt']
            assert MODELL in {x['id'] for x in (await c.get('/v1/steckbriefe')).json()['data']}
            assert MODELL in {x['id'] for x in (await c.get('/api/v0/models')).json()['data']}
            assert MODELL in {x['key'] for x in (await c.get('/api/v1/models')).json()['models']}
            assert a.agent.befehle == vorher, 'Katalogabfragen dürfen keine Dienste starten'
            r = await c.post('/v1/chat/completions', json={'model': MODELL, 'messages': []})
            assert r.status_code == 403 and r.json()['error']['code'] == 'faehigkeit_nicht_erlaubt'
            assert (await c.get('/v1/models', headers={'Authorization': 'Bearer falsch'})).status_code == 401


async def test_prognose_uebernimmt_die_auftragskoepfe(tmp_path):
    async with aufbau(tmp_path) as a:
        a.app.state.betrieb.verbund.hintergrund_erlaubt = False
        vorher = len(a.app.state.betrieb.verbund.auftraege)
        r = await a.anw.post('/v1/einschaetzung', json={'model': MODELL},
                             headers={'X-Leitstelle-Prioritaet': 'hintergrund'})
        assert r.status_code == 200
        assert not r.json()['sofort'] and 'Hintergrund' in r.json()['grund']
        r = await a.anw.post('/v1/einschaetzung', json={'model': MODELL}, headers={'X-Leitstelle-Art': 'masse'})
        assert r.status_code == 200
        assert len(a.app.state.betrieb.verbund.auftraege) == vorher
