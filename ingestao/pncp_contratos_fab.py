"""
Ingestão de contratos FAB/Defesa do PNCP (Portal Nacional de Contratações Públicas).

Busca contratos de manutenção de aeronaves e combustível para:
- Comando da Aeronáutica (CNPJ 00394429000100)
- Ministério da Defesa  (CNPJ 03277610000125)

Filtra por palavras-chave relevantes e gera dados/pncp_contratos.json
e dados/analises/pncp_contratos.md com custo bottom-up por aeronave.

Uso:
    python ingestao/pncp_contratos_fab.py
    python ingestao/pncp_contratos_fab.py --anos 2022,2023,2024,2025
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT     = Path(__file__).resolve().parent.parent
DADOS    = ROOT / "dados"
ANALISES = ROOT / "dados" / "analises"
ANALISES.mkdir(parents=True, exist_ok=True)

BASE = "https://pncp.gov.br/api/consulta/v1"

ORGAOS = {
    "FAB":    "00394429000100",
    "DEFESA": "03277610000125",
}

# Palavras-chave para filtrar contratos relevantes
TERMOS_AERONAVE = [
    "aeronave", "aircraft", "avião", "helicóptero",
    "motor", "turbina", "propulsor",
    "legacy", "embraer", "airbus", "a319", "erj",
    "vc-1", "vc-2", "vc-99", "kc-30",
    "fab2101", "fab2580", "fab2590",
    "manutenção aeronáutica", "manutenção de aeronave",
    "simulador de voo", "simulador voo",
    "peças aeronáuticas", "componentes aeronáuticos",
]

TERMOS_COMBUSTIVEL = [
    "combustível", "querosene", "avtur", "jp-8", "jp8",
    "abastecimento aeronave", "combustível aeronáutico",
    "qav", "qav-1",
]

TERMOS_RELEVANTES = TERMOS_AERONAVE + TERMOS_COMBUSTIVEL


def _gh_get(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "radar-fab/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def buscar_contratos(cnpj: str, ano: int) -> list[dict]:
    """Retorna todos os contratos de um CNPJ num ano."""
    data_ini = f"{ano}0101"
    data_fim = f"{ano}1231"
    pagina = 1
    todos: list[dict] = []

    while True:
        params = urllib.parse.urlencode({
            "dataInicial":   data_ini,
            "dataFinal":     data_fim,
            "pagina":        pagina,
            "tamanhoPagina": 500,
            "cnpjOrgao":     cnpj,
        })
        url = f"{BASE}/contratos?{params}"
        try:
            data = _gh_get(url)
        except Exception as e:
            print(f"    ERRO pág {pagina}: {e}", file=sys.stderr)
            break

        itens = data if isinstance(data, list) else data.get("data", data.get("itens", []))
        if not itens:
            break

        todos.extend(itens)
        print(f"    pág {pagina}: {len(itens)} contratos", file=sys.stderr)

        # Paginação
        total_pags = data.get("totalPaginas") if isinstance(data, dict) else None
        if total_pags and pagina >= total_pags:
            break
        if len(itens) < 500:
            break
        pagina += 1
        time.sleep(0.5)

    return todos


def is_relevante(contrato: dict) -> tuple[bool, str]:
    """Retorna (relevante, categoria)."""
    objeto = (contrato.get("objetoContrato") or
              contrato.get("descricaoObjeto") or "").lower()

    for t in TERMOS_COMBUSTIVEL:
        if t in objeto:
            return True, "combustível"
    for t in TERMOS_AERONAVE:
        if t in objeto:
            return True, "aeronave/manutenção"
    return False, ""


def extrair_campos(c: dict, orgao: str, categoria: str) -> dict:
    return {
        "orgao":        orgao,
        "categoria":    categoria,
        "id":           c.get("numeroControlePNCP") or c.get("id", ""),
        "objeto":       (c.get("objetoContrato") or c.get("descricaoObjeto") or "")[:200],
        "fornecedor":   c.get("nomeRazaoSocialFornecedor") or "",
        "valor":        c.get("valorInicial") or c.get("valorGlobal") or 0,
        "vigencia_ini": c.get("dataInicioVigencia") or c.get("dataVigenciaInicio") or "",
        "vigencia_fim": c.get("dataFimVigencia") or c.get("dataVigenciaFim") or "",
        "modalidade":   (c.get("modalidadeNome") or
                         c.get("modalidadeContratacao", {}).get("descricao") if isinstance(c.get("modalidadeContratacao"), dict) else "") or "",
    }


def gerar_md(contratos: list[dict], anos: list[int]) -> Path:
    total_valor = sum(c["valor"] for c in contratos)
    aeronave = [c for c in contratos if c["categoria"] == "aeronave/manutenção"]
    combustivel = [c for c in contratos if c["categoria"] == "combustível"]

    # Isola contratos que citam a frota VIP especificamente
    VIP = ["legacy", "a319", "a-319", "erj-190", "erj190", "vc-1", "vc-99",
           "vc99", "presidencial", "phenom", "vip"]
    vip_contratos = [c for c in contratos
                     if any(t in c["objeto"].lower() for t in VIP)]

    linhas = [
        "# Contratos FAB/Defesa — Aeronaves e Combustível (PNCP)",
        "",
        f"_Gerado em {datetime.now().strftime('%Y-%m-%d')} · "
        f"Anos: {', '.join(str(a) for a in anos)} · "
        f"{len(contratos)} contratos relevantes · "
        f"Valor total: R$ {total_valor:,.0f}_".replace(",", "."),
        "",
        "> Fonte: Portal Nacional de Contratações Públicas (PNCP) · "
        "Sem autenticação · Dados públicos.",
        ">",
        "> **ESCOPO E LIMITAÇÃO:** Estes contratos cobrem a logística da frota "
        "**inteira** da FAB (caça, transporte, treinamento), não apenas a frota "
        "VIP de transporte de autoridades. Os objetos de contrato públicos "
        "raramente citam o modelo específico (Legacy 600, A319, ERJ-190), então "
        "**não é possível isolar o custo da frota VIP** a partir do PNCP. Valor "
        "como contexto macro do gasto aeronáutico da FAB, não como custo/hora VIP.",
        "",
    ]

    if vip_contratos:
        vip_valor = sum(c["valor"] for c in vip_contratos)
        linhas += [
            f"## Contratos que citam a frota VIP ({len(vip_contratos)})",
            f"_Valor: R$ {vip_valor:,.0f} — único subconjunto isolável da frota de autoridades_".replace(",", "."),
            "",
            "| Órgão | Fornecedor | Objeto | Valor | Vigência |",
            "|---|---|---|---:|---|",
        ]
        for c in sorted(vip_contratos, key=lambda x: -x["valor"]):
            linhas.append(
                f"| {c['orgao']} | {c['fornecedor'][:28]} | {c['objeto'][:55]} "
                f"| R$ {c['valor']:,.0f} | {c['vigencia_ini'][:10]}–{c['vigencia_fim'][:10]} |".replace(",", ".")
            )
        linhas.append("")

    for titulo, grupo in [
        (f"Manutenção / Aeronaves ({len(aeronave)} contratos)", aeronave),
        (f"Combustível ({len(combustivel)} contratos)", combustivel),
    ]:
        if not grupo:
            continue
        valor_grupo = sum(c["valor"] for c in grupo)
        linhas += [
            f"## {titulo}",
            f"_Valor total: R$ {valor_grupo:,.0f}_".replace(",", "."),
            "",
            "| Órgão | Fornecedor | Objeto | Valor | Vigência |",
            "|---|---|---|---:|---|",
        ]
        for c in sorted(grupo, key=lambda x: -x["valor"]):
            linhas.append(
                f"| {c['orgao']} | {c['fornecedor'][:30]} "
                f"| {c['objeto'][:60]} "
                f"| R$ {c['valor']:,.0f} "
                f"| {c['vigencia_ini'][:10]}–{c['vigencia_fim'][:10]} |".replace(",", ".")
            )
        linhas.append("")

    dest = ANALISES / "pncp_contratos.md"
    dest.write_text("\n".join(linhas), encoding="utf-8")
    print(f"  → {dest.relative_to(ROOT)}", file=sys.stderr)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--anos", default="2023,2024,2025",
                    help="Anos separados por vírgula (padrão: 2023,2024,2025)")
    args = ap.parse_args()
    anos = [int(a.strip()) for a in args.anos.split(",")]

    todos_relevantes: list[dict] = []

    for nome_orgao, cnpj in ORGAOS.items():
        for ano in anos:
            print(f"Buscando {nome_orgao} ({ano})...", file=sys.stderr)
            contratos = buscar_contratos(cnpj, ano)
            print(f"  {len(contratos)} contratos no total", file=sys.stderr)

            for c in contratos:
                relevante, categoria = is_relevante(c)
                if relevante:
                    todos_relevantes.append(extrair_campos(c, nome_orgao, categoria))

            print(f"  {sum(1 for c in todos_relevantes if c['orgao'] == nome_orgao)} relevantes acumulados",
                  file=sys.stderr)

    print(f"\nTotal relevantes: {len(todos_relevantes)}", file=sys.stderr)
    valor_total = sum(c["valor"] for c in todos_relevantes)
    print(f"Valor total: R$ {valor_total:,.0f}".replace(",", "."), file=sys.stderr)

    # Salva JSON
    out_json = DADOS / "pncp_contratos.json"
    out_json.write_text(
        json.dumps({"_meta": {"gerado": datetime.now().isoformat(), "anos": anos},
                    "contratos": todos_relevantes},
                   indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"  → {out_json.relative_to(ROOT)}", file=sys.stderr)

    gerar_md(todos_relevantes, anos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
