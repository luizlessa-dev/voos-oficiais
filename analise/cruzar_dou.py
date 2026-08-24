"""
Cruzamento voo × Diário Oficial da União.

Para cada voo suspeito (fim de semana, sequência, destino atípico),
busca no DOU se há publicação com nome/cargo da autoridade na data
do voo. Ausência de publicação = lacuna editorial a investigar.

Uso:
    python analise/cruzar_dou.py dados/snapshots/voos_2026_04.csv
    python analise/cruzar_dou.py dados/snapshots/voos_2026_04.csv --fds
    python analise/cruzar_dou.py dados/snapshots/voos_2026_04.csv --todos

Saída: dados/analises/dou_AAAA-MM.md
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT     = Path(__file__).resolve().parent.parent
ANALISES = ROOT / "dados" / "analises"
ANALISES.mkdir(parents=True, exist_ok=True)

DOU_URL  = "https://www.in.gov.br/consulta/-/buscar/dou"
THROTTLE = 1.5  # segundos entre chamadas

# Mapeamento cargo (GABAER) → termos de busca no DOU
# O DOU cita o nome da pessoa, não o cargo — mas o cargo aparece nos atos
CARGO_TERMOS: dict[str, list[str]] = {
    # "Vice-Presidente da República" tem que vir ANTES de "Presidente da
    # República": termos_para_cargo() casa por substring nos dois sentidos,
    # e "presidente da república" é substring de "vice-presidente da
    # república" — sem essa entrada primeiro, Vice-Presidente herdava os
    # termos de busca do Lula por engano (achado testando a automação em
    # 2026-08-24, cargo nunca tinha sido cruzado com o DOU antes).
    "Vice-Presidente da República":          ["Geraldo Alckmin"],
    "Presidente da República":               ["Lula", "Luiz Inácio Lula da Silva"],
    "Presidente da Câmara dos Deputados":    ["Hugo Motta"],
    "Presidente do Congresso Nacional":      ["Davi Alcolumbre"],
    "Presidente do Supremo Tribunal Federal":["Barroso", "Luís Roberto Barroso"],
    "Ministro da Saúde":                     ["Alexandre Padilha"],
    "Ministro da Fazenda":                   ["Fernando Haddad", "Dario Durigan"],
    "Ministro da Defesa":                    ["José Múcio", "Múcio Monteiro"],
    "Ministro das Relações Exteriores":      ["Mauro Vieira"],
    "Ministro dos Transportes":              ["Renan Filho", "George Santoro"],
    "Ministro da Educação":                  ["Camilo Santana", "Leonardo Barchini"],
    "Ministro da Justiça e Segurança Pública":["Wellington César", "Lewandowski"],
    "Ministro de Portos e Aeroportos":       ["Silvio Costa Filho", "Tomé Barros"],
    "Ministro das Comunicações":             ["Frederico Siqueira"],
    "Ministro das Cidades":                  ["Jader Barbalho", "Vladimir Lima"],
    "Ministro do Trabalho e Emprego":        ["Luiz Marinho"],
    "Ministro do Turismo":                   ["Celso Sabino"],
    "Ministro Integração do Desenvolvimento Regional": ["Waldez Góes"],
    "Ministro dos Povos Indígenas":          ["Sônia Guajajara"],
    "Comandante do Exército":                ["Tomás Paiva"],
    "Comandante da Marinha":                 ["Marcos Sampaio Olsen"],
    "Comandante da Aeronáutica":             ["Marcelo Kanitz Damasceno"],
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _detectar_encoding(path: Path) -> str:
    try:
        path.read_text(encoding="utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def parse_csv(path: Path) -> list[dict]:
    voos = []
    enc = _detectar_encoding(path)
    with path.open(encoding=enc) as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)
        for row in reader:
            if not row or not row[0].strip():
                continue
            try:
                dec = datetime.strptime(row[2].strip(), "%d/%m/%Y - %H:%M")
            except (ValueError, IndexError):
                continue
            voos.append({
                "autoridade": row[0].strip(),
                "origem":     row[1].strip(),
                "decolagem":  dec,
                "destino":    row[3].strip() if len(row) > 3 else "",
                "motivo":     row[5].strip() if len(row) > 5 else "",
                "passageiros":row[6].strip() if len(row) > 6 else "",
            })
    return voos


def buscar_dou(termo: str, data: datetime, secao: str = "todos") -> list[dict]:
    """Busca no DOU por termo numa data específica."""
    params = urllib.parse.urlencode({
        "q":       f'"{termo}"',
        "secao":   secao,
        "publicado": data.strftime("%d/%m/%Y"),
    })
    url = f"{DOU_URL}?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "radar-fab-voos/1.0", "Accept": "text/html"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    ERRO ao buscar DOU: {e}", file=sys.stderr)
        return []

    # Extrai JSON embutido no HTML
    m = re.search(
        r'<script[^>]+_params[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if not m:
        return []
    try:
        data_json = json.loads(m.group(1))
        items = data_json.get("jsonArray", [])
    except Exception:
        return []

    # Filtra pela data exata (o DOU retorna por relevância, não por data)
    data_str = data.strftime("%d/%m/%Y")
    return [it for it in items if it.get("pubDate") == data_str]


def termos_para_cargo(cargo: str) -> list[str]:
    """Retorna termos de busca para o cargo, ou fragmento do cargo."""
    for padrao, termos in CARGO_TERMOS.items():
        if padrao.lower() in cargo.lower() or cargo.lower() in padrao.lower():
            return termos
    # fallback: usa palavras do cargo como termo
    palavras = [p for p in cargo.split() if len(p) > 4
                and p.lower() not in {"ministro","ministra","presidente","secretário",
                                      "secretária","comando","comandante","disposição"}]
    return palavras[:2] if palavras else [cargo[:30]]


def voos_suspeitos(voos: list[dict], modo: str) -> list[dict]:
    """Filtra voos para cruzamento conforme o modo."""
    if modo == "todos":
        return voos
    if modo == "fds":
        return [v for v in voos if v["decolagem"].weekday() >= 5]
    # modo padrão: fim de semana + sequências (3+ pernas mesmo dia)
    fds = {v["decolagem"].date() for v in voos if v["decolagem"].weekday() >= 5}
    bucket: dict = defaultdict(list)
    for v in voos:
        bucket[(v["autoridade"], v["decolagem"].date())].append(v)
    dias_seq = {dia for (_, dia), vs in bucket.items() if len(vs) >= 3}
    suspeitos = []
    seen = set()
    for v in voos:
        d = v["decolagem"].date()
        chave = (v["autoridade"], d)
        if chave in seen:
            continue
        if d in fds or d in dias_seq:
            suspeitos.append(v)
            seen.add(chave)
    return suspeitos


# ── core ─────────────────────────────────────────────────────────────────────

def cruzar(voos: list[dict], modo: str) -> list[dict]:
    """Para cada voo suspeito, busca publicações no DOU naquela data."""
    candidatos = voos_suspeitos(voos, modo)
    print(f"  {len(candidatos)} voos para cruzar com o DOU...", file=sys.stderr)

    resultados = []
    for v in candidatos:
        cargo   = v["autoridade"]
        data    = v["decolagem"]
        termos  = termos_para_cargo(cargo)

        publicacoes = []
        for termo in termos[:2]:  # máximo 2 termos por voo
            print(f"    → {data.strftime('%d/%m/%Y')} | {cargo[:40]} | '{termo}'",
                  file=sys.stderr)
            pubs = buscar_dou(termo, data)
            publicacoes.extend(pubs)
            time.sleep(THROTTLE)

        resultados.append({
            "voo":         v,
            "publicacoes": publicacoes,
            "tem_pub":     len(publicacoes) > 0,
        })

    return resultados


def gerar_md(resultados: list[dict], csv_path: Path, modo: str) -> Path:
    nome = csv_path.stem
    _, ano_s, mes_s = nome.split("_")
    ano, mes = int(ano_s), int(mes_s)

    sem_pub = [r for r in resultados if not r["tem_pub"]]
    com_pub = [r for r in resultados if r["tem_pub"]]

    linhas = [
        f"# Cruzamento Voo × DOU — {ano}-{mes:02d}",
        "",
        f"_Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
        f"Modo: {modo} · "
        f"{len(resultados)} voos analisados · "
        f"{len(sem_pub)} **sem publicação no DOU**_",
        "",
        "> Voos sem publicação correspondente no DOU na data do voo "
        "podem indicar viagem sem justificativa oficial registrada.",
        "",
    ]

    # ── Sem publicação — prioridade editorial ────────────────────────────────
    linhas += ["## ⚠️ Sem publicação no DOU (investigar)", ""]
    if sem_pub:
        linhas += ["| Data | Dia | Autoridade | Rota | Motivo |",
                   "|---|---|---|---|---|"]
        for r in sem_pub:
            v   = r["voo"]
            dia = ["seg","ter","qua","qui","sex","**SÁB**","**DOM**"][v["decolagem"].weekday()]
            linhas.append(
                f"| {v['decolagem'].strftime('%d/%m')} | {dia} "
                f"| {v['autoridade']} | {v['origem']} → {v['destino']} | {v['motivo']} |"
            )
    else:
        linhas.append("_Todos os voos analisados têm publicação correspondente no DOU._")
    linhas.append("")

    # ── Com publicação ────────────────────────────────────────────────────────
    linhas += ["## ✅ Com publicação no DOU", ""]
    for r in com_pub:
        v = r["voo"]
        linhas.append(
            f"**{v['decolagem'].strftime('%d/%m')} · {v['autoridade']}** "
            f"({v['origem']} → {v['destino']})"
        )
        for pub in r["publicacoes"][:3]:
            linhas.append(
                f"- [{pub.get('pubDate')} · {pub.get('artType','?')}] "
                f"{pub.get('title','')[:80]}"
            )
        linhas.append("")

    dest = ANALISES / f"dou_{ano:04d}-{mes:02d}.md"
    dest.write_text("\n".join(linhas), encoding="utf-8")
    print(f"  → {dest.relative_to(ROOT)}", file=sys.stderr)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="CSV em dados/snapshots/")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--fds",   action="store_true", help="Só voos de fim de semana")
    grp.add_argument("--todos", action="store_true", help="Todos os voos do mês")
    args = ap.parse_args()

    modo = "todos" if args.todos else ("fds" if args.fds else "suspeitos")
    path = Path(args.csv)
    if not path.exists():
        print(f"Arquivo não encontrado: {path}", file=sys.stderr)
        return 1

    print(f"Lendo {path.name}...", file=sys.stderr)
    voos = parse_csv(path)
    print(f"  {len(voos)} voos", file=sys.stderr)

    resultados = cruzar(voos, modo)
    gerar_md(resultados, path, modo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
