"""
Agrega todos os CSVs do GABAER (2020–hoje) num ranking explorável por
autoridade, salvo em dados/ranking.json para a página /ranking do site.

Para cada autoridade (cargo): total de voos, custo estimado, voos em FDS,
noturnos, internacionais, "à disposição", top destinos e split por governo.

Uso:
    python analise/gerar_ranking.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "dados" / "snapshots"
DADOS = ROOT / "dados"

# ── custo por cargo (espelha analisar_mes.py) ──────────────────────
CUSTO_VC1, CUSTO_LEGACY, CUSTO_MEDIO_TCU = 42_500, 34_000, 38_100

def custo_hora(cargo: str) -> int:
    c = cargo.upper()
    if "PRESIDENTE DA REPÚBLICA" in c:
        return CUSTO_VC1
    return CUSTO_LEGACY  # demais autoridades: Legacy 600 (conservador)

# ── detector internacional ─────────────────────────────────────────
_AEROPORTOS_BR = {"congonhas","santos dumont","pampulha","galeão","guarulhos",
                  "ponta pelada","eduardo gomes","parnamirim","afonsos","confins",
                  "arealva","santa cruz"}
_RE_PAREN = re.compile(r"\(([^)]+)\)")
def is_intl(local: str) -> bool:
    m = _RE_PAREN.search(local)
    return bool(m and m.group(1).strip().lower() not in _AEROPORTOS_BR)
def pais(local: str) -> str:
    m = _RE_PAREN.search(local)
    return m.group(1).strip() if m else local

def governo(ano: int) -> str:
    return "Lula 3" if ano >= 2023 else "Bolsonaro"

import unicodedata
def slug(cargo: str) -> str:
    s = unicodedata.normalize("NFD", cargo).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

def cidade_base(local: str) -> str:
    """'São Paulo (Congonhas)' → 'São Paulo'."""
    return local.split("(")[0].strip()

# Coordenadas das principais cidades-destino (lat, lng)
COORDS = {
    "Brasília": (-15.79, -47.88), "São Paulo": (-23.55, -46.63), "Rio de Janeiro": (-22.91, -43.17),
    "Maceió": (-9.67, -35.74), "Belo Horizonte": (-19.92, -43.94), "Macapá": (0.03, -51.07),
    "Belém": (-1.46, -48.50), "Canoas": (-29.92, -51.18), "São Luís": (-2.53, -44.30),
    "Fortaleza": (-3.73, -38.52), "Recife": (-8.05, -34.88), "Natal": (-5.79, -35.21),
    "Manaus": (-3.12, -60.02), "João Pessoa": (-7.12, -34.86), "Foz Do Iguaçu": (-25.52, -54.58),
    "Foz do Iguaçu": (-25.52, -54.58), "Teresina": (-5.09, -42.80), "Uberlândia": (-18.92, -48.28),
    "Aracaju": (-10.95, -37.07), "Florianópolis": (-27.59, -48.55), "Boa Vista": (2.82, -60.67),
    "São José Dos Campos": (-23.22, -45.89), "Ribeirão Preto": (-21.18, -47.81), "Cuiabá": (-15.60, -56.10),
    "Santarém": (-2.44, -54.71), "Porto Alegre": (-30.03, -51.23), "Campinas": (-22.91, -47.06),
    "Salvador": (-12.97, -38.51), "Novo Progresso": (-7.14, -55.38), "Campo Grande": (-20.47, -54.62),
    "Curitiba": (-25.43, -49.27), "Campina Grande": (-7.23, -35.88), "Patos": (-7.02, -37.28),
    "Petrolina": (-9.39, -40.50), "Goiânia": (-16.69, -49.26), "Vitória": (-20.32, -40.34),
    "Porto Velho": (-8.76, -63.90), "Rio Branco": (-9.97, -67.81), "Palmas": (-10.18, -48.33),
    "Varginha": (-21.55, -45.43), "Marabá": (-5.37, -49.13), "Presidente Prudente": (-22.13, -51.39),
    "Sorocaba": (-23.50, -47.46), "Londrina": (-23.31, -51.16), "Juazeiro Do Norte": (-7.21, -39.31),
    "Pelotas": (-31.77, -52.34), "Barreiras": (-12.15, -44.99), "Botucatu": (-22.89, -48.45),
    "Serra Talhada": (-7.99, -38.30), "Araçatuba": (-21.21, -50.43), "Jaguaruna": (-28.61, -49.02),
    "Santa Maria": (-29.68, -53.81), "Caruaru": (-8.28, -35.97), "Dourados": (-22.22, -54.81),
    "Sinop": (-11.86, -55.50), "Imperatriz": (-5.53, -47.49), "Bauru": (-22.31, -49.06),
}

def _enc(p: Path) -> str:
    try: p.read_text(encoding="utf-8"); return "utf-8"
    except UnicodeDecodeError: return "latin-1"


def carregar() -> list[dict]:
    voos = []
    for p in sorted(SNAP.glob("voos_*.csv")):
        if p.name == "rab_anac.csv":
            continue
        with p.open(encoding=_enc(p)) as f:
            r = csv.reader(f, delimiter=";")
            next(r)
            for row in r:
                if not row or not row[0].strip():
                    continue
                try:
                    dec = datetime.strptime(row[2].strip(), "%d/%m/%Y - %H:%M")
                    try: pou = datetime.strptime(row[4].strip(), "%d/%m/%Y - %H:%M")
                    except (ValueError, IndexError): pou = None
                except (ValueError, IndexError):
                    continue
                voos.append({
                    "autoridade": row[0].strip(),
                    "origem": row[1].strip(),
                    "decolagem": dec,
                    "destino": row[3].strip() if len(row) > 3 else "",
                    "pouso": pou,
                })
    return voos


def custo_voo(v: dict) -> int:
    ch = custo_hora(v["autoridade"])
    pou = v.get("pouso")
    if pou and pou > v["decolagem"]:
        h = (pou - v["decolagem"]).total_seconds() / 3600
        return round(h * ch)
    if pou and pou < v["decolagem"]:
        h = (pou + timedelta(days=1) - v["decolagem"]).total_seconds() / 3600
        return round(h * ch)
    return CUSTO_MEDIO_TCU


def main() -> int:
    voos = carregar()
    print(f"Carregados {len(voos)} voos", file=sys.stderr)

    por_autor: dict[str, dict] = defaultdict(lambda: {
        "voos": 0, "custo": 0, "fds": 0, "noturnos": 0, "intl": 0,
        "a_disposicao": 0, "destinos": Counter(), "bolsonaro": 0, "lula": 0,
    })
    dest_global: Counter = Counter()          # cidade-base → total de voos (para o mapa)
    detalhe: dict[str, dict] = defaultdict(lambda: {"voos": [], "timeline": Counter()})

    for v in voos:
        a = por_autor[v["autoridade"]]
        a["voos"] += 1
        c = custo_voo(v)
        a["custo"] += c
        if v["decolagem"].weekday() >= 5: a["fds"] += 1
        if v["decolagem"].hour >= 22 or v["decolagem"].hour < 5: a["noturnos"] += 1
        if is_intl(v["destino"]) or is_intl(v["origem"]): a["intl"] += 1
        if v["autoridade"].lower().startswith(("à disposição", "a disposição")):
            a["a_disposicao"] += 1
        if v["destino"]: a["destinos"][v["destino"]] += 1
        if governo(v["decolagem"].year) == "Lula 3": a["lula"] += 1
        else: a["bolsonaro"] += 1

        # destino-base para o mapa (só nacionais, agrupando aeroportos da mesma cidade)
        if v["destino"] and not is_intl(v["destino"]):
            dest_global[cidade_base(v["destino"])] += 1

        # detalhe por autoridade
        det = detalhe[v["autoridade"]]
        det["timeline"][v["decolagem"].strftime("%Y-%m")] += 1
        det["voos"].append({
            "data": v["decolagem"].strftime("%d/%m/%Y"),
            "origem": v["origem"], "destino": v["destino"], "custo": c,
            "fds": v["decolagem"].weekday() >= 5,
        })

    ranking = []
    for cargo, s in por_autor.items():
        ranking.append({
            "autoridade": cargo,
            "voos": s["voos"],
            "custo_estimado": s["custo"],
            "fds": s["fds"],
            "fds_pct": round(s["fds"] / s["voos"] * 100) if s["voos"] else 0,
            "noturnos": s["noturnos"],
            "internacionais": s["intl"],
            "a_disposicao": s["a_disposicao"],
            "top_destinos": [{"destino": d, "n": n} for d, n in s["destinos"].most_common(3)],
            "bolsonaro": s["bolsonaro"],
            "lula": s["lula"],
        })
    ranking.sort(key=lambda x: -x["voos"])

    total_voos = sum(r["voos"] for r in ranking)
    total_custo = sum(r["custo_estimado"] for r in ranking)
    anos = sorted({v["decolagem"].year for v in voos})

    out = {
        "_meta": {
            "gerado": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "fonte": "GABAER/COMAER · Decreto 10.267/2020",
            "periodo": f"{anos[0]}–{anos[-1]}",
            "total_voos": total_voos,
            "total_custo_estimado": total_custo,
            "total_autoridades": len(ranking),
            "nota_custo": "Estimativa: tempo real de voo × custo/hora por aeronave "
                          "(VC-1 R$42,5k/h presidencial; Legacy 600 R$34k/h demais). "
                          "Sem pouso registrado: média TCU R$38,1k/missão.",
        },
        "ranking": ranking,
    }
    dest = DADOS / "ranking.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {dest.relative_to(ROOT)}", file=sys.stderr)
    print(f"  {len(ranking)} autoridades · {total_voos} voos · "
          f"R$ {total_custo:,.0f} estimado".replace(",", "."), file=sys.stderr)

    # ── destinos.json (para o mapa) ────────────────────────────────
    destinos = []
    sem_coord = 0
    for cidade, n in dest_global.most_common():
        co = COORDS.get(cidade)
        if not co:
            sem_coord += n
            continue
        destinos.append({"cidade": cidade, "n": n, "lat": co[0], "lng": co[1]})
    dest_out = {
        "_meta": {
            "gerado": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "total_destinos_mapeados": len(destinos),
            "voos_sem_coordenada": sem_coord,
            "nota": "Voos nacionais agrupados por cidade-destino. Internacionais não entram no mapa do Brasil.",
        },
        "destinos": destinos,
    }
    (DADOS / "destinos.json").write_text(
        json.dumps(dest_out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → dados/destinos.json ({len(destinos)} cidades, {sem_coord} voos sem coord)", file=sys.stderr)

    # ── detalhe por autoridade (>= 20 voos) ────────────────────────
    AUT_DIR = DADOS / "autoridades"
    AUT_DIR.mkdir(exist_ok=True)
    gerados = 0
    for cargo, det in detalhe.items():
        if por_autor[cargo]["voos"] < 20:
            continue
        s = por_autor[cargo]
        timeline = [{"mes": m, "n": n} for m, n in sorted(det["timeline"].items())]
        # voos ordenados por data desc, limitado a 500
        voos_ord = sorted(det["voos"], key=lambda x: x["data"].split("/")[::-1], reverse=True)[:500]
        ddest = Counter(cidade_base(v["destino"]) for v in det["voos"] if v["destino"])
        payload = {
            "autoridade": cargo, "slug": slug(cargo),
            "voos": s["voos"], "custo_estimado": s["custo"],
            "fds": s["fds"], "fds_pct": round(s["fds"] / s["voos"] * 100),
            "noturnos": s["noturnos"], "internacionais": s["intl"],
            "a_disposicao": s["a_disposicao"],
            "bolsonaro": s["bolsonaro"], "lula": s["lula"],
            "top_destinos": [{"destino": d, "n": n} for d, n in ddest.most_common(10)],
            "timeline": timeline,
            "voos_lista": voos_ord,
        }
        (AUT_DIR / f"{slug(cargo)}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        gerados += 1
    print(f"  → dados/autoridades/*.json ({gerados} autoridades com ≥20 voos)", file=sys.stderr)

    # adiciona slug ao ranking principal pra linkar
    for r in ranking:
        r["slug"] = slug(r["autoridade"]) if por_autor[r["autoridade"]]["voos"] >= 20 else None
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
