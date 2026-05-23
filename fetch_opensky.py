#!/usr/bin/env python3
"""
PoC: Rastreamento de aeronaves oficiais brasileiras via OpenSky Network.

Estratégia dupla:
  1) Consulta /states/all filtrando pelo bounding box do Brasil — pega
     TODOS os states ativos sobre o território. Depois filtramos por
     callsign (FAB*, BRS*, PRPF*, etc) e por icao24 (quando conhecido).
  2) Para cada hex conhecido, faz consulta direta /states/all?icao24=<hex>
     (mais barata em rate limit, retorna só aquela aeronave se ativa).

API anônima do OpenSky tem rate limit de 100 req/dia por IP (não 10/min como
mencionado no brief — o limite real documentado em 2024+ é 100/dia anônimo,
4000/dia com login). A gente usa sleep entre requests pra ser educado.

Endpoint anônimo NÃO retorna histórico — só estado presente. Pra histórico
precisa de conta + /api/flights/aircraft.

Output:
  - resultados/snapshot_YYYY-MM-DD_HHMMSS.json
  - print no terminal: sumário + exemplos de hits
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from aeronaves import (
    AERONAVES,
    aeronaves_com_hex,
    callsign_match,
    callsign_parece_oficial,
)

OPENSKY_BASE = "https://opensky-network.org/api"

# Bounding box do território brasileiro (incluindo águas jurisdicionais)
# lat min/max, lon min/max
BBOX_BRASIL = {
    "lamin": -34.0,  # extremo sul (RS)
    "lamax": 6.0,    # extremo norte (RR)
    "lomin": -74.0,  # extremo oeste (AC)
    "lomax": -34.0,  # extremo leste (PE / águas atlânticas)
}

# Campos do /states/all (ordem fixa do array retornado pela API)
STATE_FIELDS = [
    "icao24", "callsign", "origin_country", "time_position",
    "last_contact", "longitude", "latitude", "baro_altitude",
    "on_ground", "velocity", "true_track", "vertical_rate",
    "sensors", "geo_altitude", "squawk", "spi", "position_source",
]

USER_AGENT = "voos-oficiais-poc/0.1 (Luiz Lessa - jornalismo / transparencia)"


def http_get_json(url, timeout=30):
    """GET simples retornando JSON. Usa urllib (stdlib) pra não exigir requests."""
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return json.loads(data.decode("utf-8")), resp.status, None
    except HTTPError as e:
        return None, e.code, f"HTTPError: {e.code} {e.reason}"
    except URLError as e:
        return None, None, f"URLError: {e.reason}"
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"


def parse_state(state_arr):
    """Converte array bruto do OpenSky em dict legível."""
    if not state_arr:
        return None
    out = {}
    for i, key in enumerate(STATE_FIELDS):
        out[key] = state_arr[i] if i < len(state_arr) else None
    # normaliza callsign
    if out.get("callsign"):
        out["callsign"] = out["callsign"].strip()
    # converte timestamps unix p/ ISO
    for k in ("time_position", "last_contact"):
        if out.get(k):
            try:
                out[k + "_iso"] = datetime.fromtimestamp(out[k], tz=timezone.utc).isoformat()
            except Exception:
                pass
    return out


def consulta_bbox_brasil():
    """Puxa TODOS os states no bounding box do Brasil."""
    qs = urlencode(BBOX_BRASIL)
    url = f"{OPENSKY_BASE}/states/all?{qs}"
    print(f"[1] GET {url}")
    data, status, err = http_get_json(url)
    if err:
        print(f"    ERRO: {err} (status={status})")
        return None
    if not data or "states" not in data:
        print(f"    Resposta inesperada: {str(data)[:200]}")
        return None
    states = data.get("states") or []
    print(f"    OK — {len(states)} aeronaves no bbox Brasil (timestamp {data.get('time')})")
    return states


def consulta_hex(icao24_hex):
    """Consulta um hex específico (mais barato em rate limit)."""
    url = f"{OPENSKY_BASE}/states/all?icao24={icao24_hex.lower()}"
    data, status, err = http_get_json(url)
    if err:
        return None, err
    states = (data or {}).get("states") or []
    return states, None


def main():
    print("=" * 70)
    print("PoC — Aeronaves Oficiais Brasileiras via OpenSky Network")
    print(f"Timestamp UTC: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    com_hex = aeronaves_com_hex()
    print(f"\nAeronaves curadas no total: {len(AERONAVES)}")
    print(f"Com hex ICAO conhecido (consulta direta): {len(com_hex)}")
    print(f"Só callsign (precisam aparecer no bbox): {len(AERONAVES) - len(com_hex)}")

    snapshot = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "metodologia": {
            "endpoint": "OpenSky /api/states/all (anônimo)",
            "bbox_brasil": BBOX_BRASIL,
            "rate_limit_observado": "100 req/dia anônimo",
        },
        "aeronaves_consultadas": len(AERONAVES),
        "aeronaves_com_hex": len(com_hex),
        "consultas_diretas_por_hex": [],
        "states_no_bbox_brasil": 0,
        "hits_por_callsign": [],
        "hits_por_hex": [],
        "callsigns_oficiais_detectados_amplos": [],
        "amostra_states_bbox": [],
        "erros": [],
    }

    # ============================================================
    # FASE 1 — Bounding box Brasil (uma req pega tudo)
    # ============================================================
    print("\n--- FASE 1: states no bbox Brasil ---")
    states = consulta_bbox_brasil()
    if states is None:
        snapshot["erros"].append("Falha consulta bbox Brasil")
        states = []
    snapshot["states_no_bbox_brasil"] = len(states)

    # Cruza com aeronaves curadas (por callsign E por icao24)
    hits_callsign = []
    hits_hex = []
    callsigns_oficiais_amplos = []

    hex_curados = {a["icao24_hex"].lower(): a for a in com_hex}

    for raw in states:
        st = parse_state(raw)
        if not st:
            continue
        cs = st.get("callsign") or ""
        hex_obs = (st.get("icao24") or "").lower()

        # Match exato por icao24 hex curado
        if hex_obs in hex_curados:
            hit = {
                "match_tipo": "hex_curado",
                "aeronave": hex_curados[hex_obs]["matricula"],
                "operador": hex_curados[hex_obs]["operador"],
                "modelo": hex_curados[hex_obs]["modelo"],
                "state": st,
            }
            hits_hex.append(hit)
            continue

        # Match por callsign exato com aeronaves curadas
        matched = False
        for aeronave in AERONAVES:
            if callsign_match(cs, aeronave):
                hits_callsign.append({
                    "match_tipo": "callsign_curado",
                    "aeronave": aeronave["matricula"],
                    "operador": aeronave["operador"],
                    "modelo": aeronave["modelo"],
                    "state": st,
                })
                matched = True
                break

        # Detecção ampla (callsign parece oficial mesmo não estando na lista)
        if not matched and callsign_parece_oficial(cs):
            callsigns_oficiais_amplos.append(st)

    snapshot["hits_por_callsign"] = hits_callsign
    snapshot["hits_por_hex"] = hits_hex
    snapshot["callsigns_oficiais_detectados_amplos"] = callsigns_oficiais_amplos
    # amostra pra olho humano: primeiros 5 states do bbox
    snapshot["amostra_states_bbox"] = [parse_state(s) for s in states[:5]]

    # ============================================================
    # FASE 2 — Consulta direta por hex (pra aeronaves fora do bbox)
    # ============================================================
    print(f"\n--- FASE 2: consulta direta por hex ({len(com_hex)} aeronaves) ---")
    print("    (pra pegar aeronaves voando fora do Brasil, ex: Lula no exterior)")
    for aeronave in com_hex:
        hex_code = aeronave["icao24_hex"]
        print(f"    GET icao24={hex_code} ({aeronave['matricula']})...")
        hits, err = consulta_hex(hex_code)
        rec = {
            "icao24_hex": hex_code,
            "matricula": aeronave["matricula"],
            "operador": aeronave["operador"],
            "ativo": False,
            "state": None,
            "erro": err,
        }
        if err:
            print(f"      ERRO: {err}")
            snapshot["erros"].append(f"{hex_code}: {err}")
        elif hits:
            rec["ativo"] = True
            rec["state"] = parse_state(hits[0])
            print(f"      ATIVO: callsign={rec['state'].get('callsign')} "
                  f"lat={rec['state'].get('latitude')} "
                  f"lon={rec['state'].get('longitude')} "
                  f"alt={rec['state'].get('baro_altitude')}m")
        else:
            print("      inativo (sem state retornado)")
        snapshot["consultas_diretas_por_hex"].append(rec)
        time.sleep(6)  # rate limit educado (~10 req/min)

    # ============================================================
    # SUMÁRIO
    # ============================================================
    print("\n" + "=" * 70)
    print("SUMÁRIO")
    print("=" * 70)
    print(f"  Aeronaves curadas:                {len(AERONAVES)}")
    print(f"  Com hex ICAO confirmado:          {len(com_hex)}")
    print(f"  States no bbox Brasil:            {snapshot['states_no_bbox_brasil']}")
    print(f"  Hits por hex (Fase 1+2):          {len(hits_hex) + sum(1 for r in snapshot['consultas_diretas_por_hex'] if r['ativo'])}")
    print(f"  Hits por callsign curado:         {len(hits_callsign)}")
    print(f"  Callsigns 'oficiais' detectados:  {len(callsigns_oficiais_amplos)}")
    print(f"  Erros:                            {len(snapshot['erros'])}")

    if hits_callsign:
        print("\n  HITS POR CALLSIGN CURADO:")
        for h in hits_callsign[:10]:
            st = h["state"]
            print(f"    - {h['aeronave']:10} {st.get('callsign','?'):10} "
                  f"lat={st.get('latitude')} lon={st.get('longitude')} "
                  f"alt={st.get('baro_altitude')}m vel={st.get('velocity')}m/s")

    if callsigns_oficiais_amplos:
        print("\n  CALLSIGNS COM PADRÃO OFICIAL (detecção ampla, não na lista curada):")
        for st in callsigns_oficiais_amplos[:15]:
            print(f"    - {st.get('callsign','?'):12} hex={st.get('icao24'):8} "
                  f"lat={st.get('latitude')} lon={st.get('longitude')} "
                  f"alt={st.get('baro_altitude')}m on_ground={st.get('on_ground')}")

    # Salva snapshot
    os.makedirs("resultados", exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    out_path = f"resultados/snapshot_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  Snapshot salvo em: {out_path}")
    print()


if __name__ == "__main__":
    main()
