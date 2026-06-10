"""
Agrega os relatórios de comitiva do Portal (portal_AAAA-MM.md) num único
dados/comitiva.json, indexado por slug de autoridade, para exibição na
página /autoridade/[slug] do site.

Lê o markdown gerado por cruzar_portal.py e extrai, por voo, os servidores
co-viajantes identificados.

Uso:
    python analise/agregar_comitiva.py
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANALISES = ROOT / "dados" / "analises"
DADOS = ROOT / "dados"

def slug(cargo: str) -> str:
    s = unicodedata.normalize("NFD", cargo).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

# Cabeçalho de bloco: "### 25/04 · Ministro da Saúde → Varginha (6 passageiros no GABAER)"
RE_HEADER = re.compile(
    r"^### (\d{2}/\d{2}) · (.+?) → (.+?) \((\d+) passageiros no GABAER\)"
)
# Linha de tabela: "| NOME | CARGO | R$ 375 | R$ 0 | Motivo |"
RE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|")


def main() -> int:
    arquivos = sorted(ANALISES.glob("portal_*.md"))
    if not arquivos:
        print("Nenhum portal_*.md encontrado.", file=sys.stderr)
        return 1

    # slug → { voo_key: {data, destino, pax, servidores: [...] } }
    por_aut: dict[str, dict] = defaultdict(dict)

    for arq in arquivos:
        mes = arq.stem.replace("portal_", "")
        linhas = arq.read_text(encoding="utf-8").splitlines()
        atual = None  # (slug, voo_key)
        for ln in linhas:
            mh = RE_HEADER.match(ln)
            if mh:
                data, cargo, destino, pax = mh.groups()
                sg = slug(cargo)
                voo_key = f"{mes}-{data}-{destino}"
                por_aut[sg].setdefault(voo_key, {
                    "data": data, "mes": mes, "destino": destino.strip(),
                    "pax": int(pax), "servidores": [],
                })
                atual = (sg, voo_key)
                continue
            if atual and ln.startswith("|") and "Servidor" not in ln and "---" not in ln:
                mr = RE_ROW.match(ln)
                if mr:
                    nome, cargo_serv, diaria, passagem, motivo = mr.groups()
                    if nome and nome != "Servidor":
                        por_aut[atual[0]][atual[1]]["servidores"].append({
                            "nome": nome.strip(),
                            "cargo": cargo_serv.strip(),
                            "diaria": diaria.strip(),
                            "passagem": passagem.strip(),
                            "motivo": motivo.strip(),
                        })

    # Converte para estrutura final
    saida = {}
    total_voos = total_serv = 0
    for sg, voos in por_aut.items():
        lista = sorted(voos.values(), key=lambda v: (v["mes"], v["data"]))
        lista = [v for v in lista if v["servidores"]]
        if not lista:
            continue
        saida[sg] = lista
        total_voos += len(lista)
        total_serv += sum(len(v["servidores"]) for v in lista)

    meses_cobertos = sorted({v["mes"] for voos in saida.values() for v in voos})
    cobertura = (f"{meses_cobertos[0]} a {meses_cobertos[-1]} (ministérios do Executivo)"
                 if meses_cobertos else "—")
    out = {
        "_meta": {
            "fonte": "Portal da Transparência (SCDP) × GABAER",
            "cobertura": cobertura,
            "nota": "Servidores do mesmo órgão que viajaram ao destino do voo FAB "
                    "nas mesmas datas. NÃO prova que estavam na aeronave — ponto de "
                    "partida de apuração.",
            "total_voos": total_voos,
            "total_servidores": total_serv,
        },
        "comitivas": saida,
    }
    (DADOS / "comitiva.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → dados/comitiva.json", file=sys.stderr)
    print(f"  {len(saida)} autoridades · {total_voos} voos · {total_serv} servidores",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
