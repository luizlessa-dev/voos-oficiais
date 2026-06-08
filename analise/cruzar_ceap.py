"""
Cruzamento voo FAB × CEAP (Cota Parlamentar) — deputados.

A única autoridade do GABAER que também é deputado com CEAP é o
Presidente da Câmara. Este script cruza as passagens aéreas lançadas
no CEAP do gabinete com as datas dos voos FAB do parlamentar.

SINAL: passagem comercial no CEAP em data de voo FAB (±1 dia). Levanta
a questão de por que um parlamentar com aeronave da FAB à disposição
ainda gera gasto com bilhetes comerciais.

LIMITAÇÃO (importante): o CEAP de um deputado pode pagar passagem de
ASSESSORES, não apenas do próprio parlamentar. Este cruzamento NÃO prova
dupla cobrança pessoal — indica gasto paralelo do gabinete a investigar.

Requer no ambiente:
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY  (base do BR Insider)

Uso:
    python analise/cruzar_ceap.py --deputado 160674 --nome "Hugo Motta" --desde 2025-02-01
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT     = Path(__file__).resolve().parent.parent
SNAP     = ROOT / "dados" / "snapshots"
ANALISES = ROOT / "dados" / "analises"
ANALISES.mkdir(parents=True, exist_ok=True)


def supa_get(path: str, url: str, key: str) -> list:
    req = urllib.request.Request(
        f"{url}/rest/v1/{path}",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


def _enc(p: Path) -> str:
    try: p.read_text(encoding="utf-8"); return "utf-8"
    except UnicodeDecodeError: return "latin-1"


def voos_presidente_camara(desde: datetime) -> list[dict]:
    voos = []
    for p in sorted(SNAP.glob("voos_*.csv")):
        with p.open(encoding=_enc(p)) as f:
            r = csv.reader(f, delimiter=";"); next(r)
            for row in r:
                if not row or not row[0].strip(): continue
                if "câmara dos deputados" not in row[0].lower(): continue
                try: dec = datetime.strptime(row[2].strip(), "%d/%m/%Y - %H:%M")
                except (ValueError, IndexError): continue
                if dec >= desde:
                    voos.append({"data": dec.date(),
                                 "origem": row[1].strip(),
                                 "destino": row[3].strip() if len(row) > 3 else ""})
    return voos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deputado", required=True, help="id_externo do deputado")
    ap.add_argument("--nome", default="Deputado")
    ap.add_argument("--desde", default="2025-02-01", help="AAAA-MM-DD")
    ap.add_argument("--url", default=os.environ.get("SUPABASE_URL", ""))
    ap.add_argument("--key", default=os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))
    args = ap.parse_args()

    if not args.url or not args.key:
        print("ERRO: defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return 1

    desde = datetime.strptime(args.desde, "%Y-%m-%d")

    # CEAP — passagens aéreas do deputado
    q = (f"ceaps_brutas?deputado_id_externo=eq.{args.deputado}"
         f"&tipo_despesa=like.PASSAGEM%20A%C3%89REA*"
         f"&select=data_documento,valor_liquido,nome_fornecedor&order=data_documento")
    ceap = supa_get(q, args.url, args.key)
    ceap = [c for c in ceap
            if c["data_documento"] >= args.desde
            and float(c["valor_liquido"] or 0) > 0]

    voos = voos_presidente_camara(desde)
    datas_fab = {v["data"] for v in voos}

    # Cruzamento ±1 dia
    matches = []
    for c in ceap:
        d = datetime.strptime(c["data_documento"], "%Y-%m-%d").date()
        for vf in voos:
            if abs((d - vf["data"]).days) <= 1:
                matches.append((c, vf))
                break

    total_ceap = sum(float(c["valor_liquido"]) for c in ceap)
    total_match = sum(float(c["valor_liquido"]) for c, _ in matches)

    linhas = [
        f"# Cruzamento Voo FAB × CEAP — {args.nome}",
        "",
        f"_Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
        f"Desde {args.desde} · {len(ceap)} passagens CEAP · "
        f"{len(voos)} voos FAB · {len(matches)} coincidências de data_",
        "",
        f"- **Passagens comerciais no CEAP** (após acesso à FAB): {len(ceap)} · "
        f"R$ {total_ceap:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        f"- **Coincidentes com voo FAB (±1 dia)**: {len(matches)} · "
        f"R$ {total_match:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "",
        "> **O que isto levanta:** por que um parlamentar com aeronave da FAB à "
        "disposição gera gasto com bilhetes comerciais no CEAP, parte deles nas "
        "mesmas datas de seus voos oficiais?",
        ">",
        "> **O que isto NÃO prova:** que o bilhete era do próprio parlamentar. O "
        "CEAP custeia passagens de assessores do gabinete. É gasto paralelo a "
        "investigar (quem voou?), não dupla cobrança pessoal comprovada.",
        "",
        "## Passagens CEAP em data de voo FAB (±1 dia)",
        "",
        "| Data CEAP | Valor | Companhia | Voo FAB coincidente |",
        "|---|---:|---|---|",
    ]
    for c, vf in sorted(matches, key=lambda x: x[0]["data_documento"]):
        v = float(c["valor_liquido"])
        linhas.append(
            f"| {c['data_documento']} | R$ {v:,.2f} | {c['nome_fornecedor'][:20]} "
            f"| {vf['data']} {vf['origem'][:16]}→{vf['destino'][:16]} |".replace(",", "X").replace(".", ",").replace("X", ".")
        )

    dest = ANALISES / f"ceap_{args.deputado}.md"
    dest.write_text("\n".join(linhas), encoding="utf-8")
    print(f"  → {dest.relative_to(ROOT)}", file=sys.stderr)
    print(f"  {len(matches)} coincidências · R$ {total_match:,.2f} coincidente", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
