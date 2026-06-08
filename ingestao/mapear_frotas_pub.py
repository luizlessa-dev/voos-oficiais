"""
Mapeamento de frotas de aeronaves de órgãos públicos não-FAB via RAB/ANAC.

Baixa o CSV do Registro Aeronáutico Brasileiro, filtra aeronaves ativas de
órgãos governamentais (PF, PRF, Polícia Militar, Civil, Bombeiros, governos
estaduais) e gera dados/frotas_pub.json + dados/analises/frotas_pub.md.

Uso:
    python ingestao/mapear_frotas_pub.py
    python ingestao/mapear_frotas_pub.py --cache   # reutiliza download anterior
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT     = Path(__file__).resolve().parent.parent
DADOS    = ROOT / "dados"
ANALISES = ROOT / "dados" / "analises"
ANALISES.mkdir(parents=True, exist_ok=True)

RAB_URL  = "https://sistemas.anac.gov.br/dadosabertos/Aeronaves/RAB/dados_aeronaves.csv"
RAB_CACHE = ROOT / "dados" / "snapshots" / "rab_anac.csv"

# ── Termos que identificam operadores públicos não-FAB ────────────────────────
TERMOS_GOV = [
    "POLICIA FEDERAL", "POLÍCIA FEDERAL",
    "POLICIA RODOVIARIA FEDERAL", "POLÍCIA RODOVIÁRIA FEDERAL",
    "GOVERNO DO ESTADO", "GOVERNO DE",
    "POLICIA MILITAR", "POLÍCIA MILITAR",
    "POLICIA CIVIL", "POLÍCIA CIVIL",
    "CORPO DE BOMBEIROS",
    "SECRETARIA DE SEGURANCA", "SECRETARIA DE SEGURANÇA",
    "SECRETARIA DA SEGURANCA", "SECRETARIA DA SEGURANÇA",
    "SECRETARIA DE ESTADO DE SEGURANCA", "SECRETARIA DE ESTADO DE SEGURANÇA",
    "SECRETARIA DE ESTADO DA SEGURANCA", "SECRETARIA DE ESTADO DA SEGURANÇA",
    "SECRETARIA DA CASA MILITAR",
    "CASA MILITAR",
    "MINISTERIO DA JUSTICA", "MINISTÉRIO DA JUSTIÇA",
    "MJ-DEPARTAMENTO",
    "DEPARTAMENTO DE POLICIA FEDERAL", "DEPARTAMENTO DE POLÍCIA FEDERAL",
    "DRACCO",
    # ── Agências/órgãos federais civis (nomes completos p/ evitar falso positivo)
    "INSTITUTO BRASILEIRO DO MEIO AMBIENTE",            # IBAMA
    "INSTITUTO CHICO MENDES",                            # ICMBio
    "INSTITUTO NACIONAL DE COLONIZACAO",                 # INCRA
    "INSTITUTO NACIONAL DE COLONIZAÇÃO",
    "AGENCIA NACIONAL DE AVIACAO CIVIL",                 # ANAC
    "AGÊNCIA NACIONAL DE AVIAÇÃO CIVIL",
    "FUNDACAO NACIONAL DOS POVOS INDIGENAS",             # FUNAI
    "FUNDAÇÃO NACIONAL DOS POVOS INDÍGENAS",
    "FUNDACAO NACIONAL DO INDIO", "FUNDAÇÃO NACIONAL DO ÍNDIO",
    "INSTITUTO NACIONAL DE PESQUISAS ESPACIAIS",         # INPE
    "INSTITUTO NACIONAL DE PESQUISAS DA AMAZONIA",       # INPA
    "UNIVERSIDADE FEDERAL",
    "DEPARTAMENTO NACIONAL DE INFRAESTRUTURA",           # DNIT
    "INSTITUTO CHICO MENDES DE CONSERVACAO",
    "MINISTERIO DO MEIO AMBIENTE", "MINISTÉRIO DO MEIO AMBIENTE",
    "MINISTERIO DA AGRICULTURA", "MINISTÉRIO DA AGRICULTURA",
    "MINISTERIO DA SAUDE", "MINISTÉRIO DA SAÚDE",
    # ── Governos municipais
    "PREFEITURA",
    "MUNICIPIO DE", "MUNICÍPIO DE",
    "GOVERNO MUNICIPAL",
]

# Termos que identificam FAB/Forças Armadas — excluir (cobertos pelo GABAER)
EXCLUIR = [
    "AERONAUTICA", "AERONÁUTICA", "FORCA AEREA", "FORÇA AÉREA",
    "COMAER", "MARINHA DO BRASIL", "EXERCITO BRASILEIRO", "EXÉRCITO BRASILEIRO",
]

# Categorização por prefixo do nome normalizado
CATEGORIAS = [
    ("Polícia Federal",          ["POLICIA FEDERAL", "POLÍCIA FEDERAL",
                                   "DEPARTAMENTO DE POLICIA FEDERAL",
                                   "MJ-DEPARTAMENTO"]),
    ("Polícia Rodoviária Federal",["POLICIA RODOVIARIA FEDERAL",
                                   "POLÍCIA RODOVIÁRIA FEDERAL"]),
    ("Polícia Militar",          ["POLICIA MILITAR", "POLÍCIA MILITAR",
                                   "PM DO ESTADO", "PMDF"]),
    ("Polícia Civil",            ["POLICIA CIVIL", "POLÍCIA CIVIL", "DRACCO"]),
    ("Corpo de Bombeiros",       ["CORPO DE BOMBEIROS"]),
    ("Órgão Federal Civil",      ["INSTITUTO BRASILEIRO DO MEIO AMBIENTE",
                                   "INSTITUTO CHICO MENDES",
                                   "INSTITUTO NACIONAL DE COLONIZACAO", "INSTITUTO NACIONAL DE COLONIZAÇÃO",
                                   "AGENCIA NACIONAL DE AVIACAO", "AGÊNCIA NACIONAL DE AVIAÇÃO",
                                   "FUNDACAO NACIONAL", "FUNDAÇÃO NACIONAL",
                                   "INSTITUTO NACIONAL DE PESQUISAS",
                                   "UNIVERSIDADE FEDERAL",
                                   "DEPARTAMENTO NACIONAL DE INFRAESTRUTURA",
                                   "MINISTERIO DO MEIO AMBIENTE", "MINISTÉRIO DO MEIO AMBIENTE",
                                   "MINISTERIO DA AGRICULTURA", "MINISTÉRIO DA AGRICULTURA",
                                   "MINISTERIO DA SAUDE", "MINISTÉRIO DA SAÚDE",
                                   "MINISTERIO DA JUSTICA", "MINISTÉRIO DA JUSTIÇA",
                                   "MJ-DEPARTAMENTO"]),
    ("Governo Municipal",        ["PREFEITURA", "MUNICIPIO DE", "MUNICÍPIO DE",
                                   "GOVERNO MUNICIPAL"]),
    ("Governo Estadual",         ["GOVERNO DO ESTADO", "GOVERNO DE",
                                   "SECRETARIA", "CASA MILITAR", "GEES"]),
]


def _norm(s: str) -> str:
    """Normaliza para uppercase sem acentos."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().upper()


def categorizar(nome: str) -> str:
    n = _norm(nome)
    for cat, prefixos in CATEGORIAS:
        if any(p in n for p in [_norm(p) for p in prefixos]):
            return cat
    return "Outro"


def parse_json_col(s: str) -> list[dict]:
    s = s.strip()
    if not s or s in ('[]', '""', ""):
        return []
    try:
        return json.loads(s)
    except Exception:
        return []


def nome_gov(entidades: list[dict]) -> str | None:
    for e in entidades:
        nome = e.get("NOME", "").upper()
        if any(ex in _norm(nome) for ex in [_norm(x) for x in EXCLUIR]):
            return None
        if any(_norm(t) in _norm(nome) for t in TERMOS_GOV):
            return e.get("NOME", "").strip()
    return None


def baixar_rab(cache: bool = False) -> Path:
    if cache and RAB_CACHE.exists():
        print(f"  Usando cache: {RAB_CACHE}", file=sys.stderr)
        return RAB_CACHE
    print(f"  Baixando RAB de {RAB_URL}...", file=sys.stderr)
    req = urllib.request.Request(RAB_URL, headers={"User-Agent": "radar-fab/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    RAB_CACHE.write_bytes(data)
    print(f"  → {len(data):,} bytes salvos em {RAB_CACHE}", file=sys.stderr)
    return RAB_CACHE


def processar(rab_path: Path) -> dict:
    """Retorna estrutura {categoria: {orgao: [aeronaves]}}."""
    resultado: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    with rab_path.open(encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)  # linha de metadado (data de atualização)
        header = [h.strip().strip('"') for h in next(reader)]

        def col(nome):
            return header.index(nome)

        idx_marca  = col("MARCAS")
        idx_prop   = col("PROPRIETARIOS")
        idx_oper   = col("OPERADORES")
        idx_model  = col("DS_MODELO")
        idx_fab    = col("NM_FABRICANTE")
        idx_tipo   = col("CD_TIPO")
        idx_icao   = col("CD_TIPO_ICAO")
        idx_pax    = col("NR_PASSAGEIROS_MAX")
        idx_ano    = col("NR_ANO_FABRICACAO")
        idx_canc   = col("DT_CANC")
        idx_uf_list = None
        for extra in ["UF", "CD_UF"]:
            if extra in header:
                idx_uf_list = col(extra)
                break

        for row in reader:
            if len(row) <= max(idx_marca, idx_oper, idx_prop):
                continue
            # Ignora aeronaves canceladas
            if row[idx_canc].strip():
                continue

            props = parse_json_col(row[idx_prop])
            opers = parse_json_col(row[idx_oper])

            nome = nome_gov(opers) or nome_gov(props)
            if not nome:
                continue

            # UF do proprietário principal
            uf = ""
            if props:
                uf = props[0].get("UF", "")

            cat = categorizar(nome)
            resultado[cat][nome].append({
                "marca":     row[idx_marca].strip().strip('"'),
                "modelo":    row[idx_model].strip().strip('"'),
                "fabricante":row[idx_fab].strip().strip('"'),
                "tipo":      row[idx_tipo].strip().strip('"'),
                "icao":      row[idx_icao].strip().strip('"'),
                "pax_max":   row[idx_pax].strip().strip('"'),
                "ano":       row[idx_ano].strip().strip('"'),
                "uf":        uf,
            })

    return {cat: dict(orgs) for cat, orgs in resultado.items()}


def gerar_json(resultado: dict, data_rab: str) -> Path:
    total = sum(len(av) for orgs in resultado.values() for av in orgs.values())
    out = {
        "_meta": {
            "descricao": "Frotas de aeronaves de órgãos públicos não-FAB registradas no RAB/ANAC.",
            "fonte": "Registro Aeronáutico Brasileiro (ANAC)",
            "url": RAB_URL,
            "data_rab": data_rab,
            "gerado": datetime.now().strftime("%Y-%m-%d"),
            "total_aeronaves": total,
            "nota": "Exclui aeronaves da Aeronáutica/FAB (cobertas pelo GABAER). "
                    "Inclui aeronaves ativas (sem data de cancelamento).",
        },
        "frotas": resultado,
    }
    dest = DADOS / "frotas_pub.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  → {dest.relative_to(ROOT)}", file=sys.stderr)
    return dest


def gerar_md(resultado: dict, data_rab: str) -> Path:
    total = sum(len(av) for orgs in resultado.values() for av in orgs.values())
    n_orgaos = sum(len(orgs) for orgs in resultado.values())

    linhas = [
        "# Frotas de Aeronaves — Órgãos Públicos Não-FAB",
        "",
        f"_Gerado em {datetime.now().strftime('%Y-%m-%d')} · "
        f"Fonte: [RAB/ANAC]({RAB_URL}) · "
        f"Dados de {data_rab} · "
        f"**{total} aeronaves ativas** em {n_orgaos} órgãos_",
        "",
        "> Exclui aeronaves da FAB/Aeronáutica (cobertas pelo GABAER/Decreto 10.267/2020).",
        "",
    ]

    for cat, orgs in sorted(resultado.items()):
        n_cat = sum(len(av) for av in orgs.values())
        linhas += [f"## {cat} ({n_cat} aeronaves)", ""]

        # Tabela resumo por órgão
        linhas += ["| Órgão | UF | Aeronaves |", "|---|---|---:|"]
        for org, aeronaves in sorted(orgs.items(), key=lambda x: -len(x[1])):
            uf = aeronaves[0].get("uf", "") if aeronaves else ""
            linhas.append(f"| {org} | {uf} | {len(aeronaves)} |")
        linhas.append("")

        # Detalhe por órgão (modelos)
        for org, aeronaves in sorted(orgs.items(), key=lambda x: -len(x[1])):
            linhas += [f"### {org}", ""]
            linhas += ["| Marca | Modelo | Fabricante | Tipo ICAO | Pax | Ano |",
                       "|---|---|---|---|---:|---|"]
            for av in sorted(aeronaves, key=lambda x: x["marca"]):
                linhas.append(
                    f"| {av['marca']} | {av['modelo']} | {av['fabricante']} "
                    f"| {av['icao']} | {av['pax_max']} | {av['ano']} |"
                )
            linhas.append("")

    dest = ANALISES / "frotas_pub.md"
    dest.write_text("\n".join(linhas), encoding="utf-8")
    print(f"  → {dest.relative_to(ROOT)}", file=sys.stderr)
    return dest


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", action="store_true", help="Reutiliza download anterior")
    args = ap.parse_args()

    rab_path = baixar_rab(cache=args.cache)

    # Extrai data de atualização da primeira linha
    with rab_path.open(encoding="utf-8-sig", errors="replace") as f:
        data_rab = f.readline().strip().replace("Atualizado em: ", "")

    print("Processando RAB...", file=sys.stderr)
    resultado = processar(rab_path)

    total = sum(len(av) for orgs in resultado.values() for av in orgs.values())
    n_org = sum(len(orgs) for orgs in resultado.values())
    print(f"  {total} aeronaves ativas em {n_org} órgãos", file=sys.stderr)
    for cat, orgs in sorted(resultado.items()):
        n = sum(len(av) for av in orgs.values())
        print(f"  {n:4d}  {cat}", file=sys.stderr)

    gerar_json(resultado, data_rab)
    gerar_md(resultado, data_rab)

    return 0


if __name__ == "__main__":
    sys.exit(main())
