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

    for v in voos:
        a = por_autor[v["autoridade"]]
        a["voos"] += 1
        a["custo"] += custo_voo(v)
        if v["decolagem"].weekday() >= 5: a["fds"] += 1
        if v["decolagem"].hour >= 22 or v["decolagem"].hour < 5: a["noturnos"] += 1
        if is_intl(v["destino"]) or is_intl(v["origem"]): a["intl"] += 1
        if v["autoridade"].lower().startswith(("à disposição", "a disposição")):
            a["a_disposicao"] += 1
        if v["destino"]: a["destinos"][v["destino"]] += 1
        if governo(v["decolagem"].year) == "Lula 3": a["lula"] += 1
        else: a["bolsonaro"] += 1

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
