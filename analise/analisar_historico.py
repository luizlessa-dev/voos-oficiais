"""
Análise histórica comparativa — agrega todos os CSVs do GABAER
(anuais 2020–2025 + mensais 2026) e gera dados/analises/historico.md.

Seções:
  1. Total de voos por ano
  2. Comparativo Bolsonaro (2020–2022) vs Lula (2023–hoje)
  3. Top 15 autoridades de todos os tempos
  4. Destinos mais frequentes por governo
  5. Tendência de voos em FDS e noturnos
  6. Meses com mais voos (picos — eleições, crises)

Uso:
    python analise/analisar_historico.py
    python analise/analisar_historico.py --stdout
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "dados" / "snapshots"
ANALISES  = ROOT / "dados" / "analises"
ANALISES.mkdir(parents=True, exist_ok=True)

GOVERNOS = {
    "Bolsonaro": (2020, 2022),
    "Lula 3":    (2023, 9999),
}
DIA_CURTO = ["seg", "ter", "qua", "qui", "sex", "SÁB", "DOM"]


# ────────────────────────── leitura ──────────────────────────

def _enc(path: Path) -> str:
    try:
        path.read_text(encoding="utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def _parse_dt(s: str) -> datetime | None:
    for fmt in ("%d/%m/%Y - %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            pass
    return None


def ler_csv(path: Path) -> list[dict]:
    voos = []
    enc = _enc(path)
    with path.open(encoding=enc) as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)  # header
        for row in reader:
            if not row or not row[0].strip():
                continue
            dec = _parse_dt(row[2]) if len(row) > 2 else None
            if dec is None:
                continue
            voos.append({
                "autoridade": row[0].strip(),
                "origem":     row[1].strip() if len(row) > 1 else "",
                "decolagem":  dec,
                "destino":    row[3].strip() if len(row) > 3 else "",
                "motivo":     row[5].strip() if len(row) > 5 else "",
                "passageiros":row[6].strip() if len(row) > 6 else "",
            })
    return voos


def carregar_todos() -> dict[int, list[dict]]:
    """Retorna dict {ano: [voos]} juntando anuais e mensais de 2026."""
    por_ano: dict[int, list[dict]] = defaultdict(list)

    # Anuais 2020–2025
    for path in sorted(SNAPSHOTS.glob("voos_*_anual.csv")):
        m = re.search(r"voos_(\d{4})_anual\.csv", path.name)
        if not m:
            continue
        ano = int(m.group(1))
        voos = ler_csv(path)
        print(f"  {path.name}: {len(voos)} voos", file=sys.stderr)
        por_ano[ano].extend(voos)

    # Mensais 2026 (e futuros)
    for path in sorted(SNAPSHOTS.glob("voos_*_??.csv")):
        m = re.search(r"voos_(\d{4})_(\d{2})\.csv", path.name)
        if not m:
            continue
        ano = int(m.group(1))
        voos = ler_csv(path)
        print(f"  {path.name}: {len(voos)} voos", file=sys.stderr)
        por_ano[ano].extend(voos)

    return dict(sorted(por_ano.items()))


# ────────────────────────── helpers ──────────────────────────

def governo_de(ano: int) -> str:
    for gov, (ini, fim) in GOVERNOS.items():
        if ini <= ano <= fim:
            return gov
    return "?"


def _pct(n: int, total: int) -> str:
    return f"{n/total*100:.1f}%" if total else "—"


# ────────────────────────── seções ──────────────────────────

def secao_totais(por_ano: dict[int, list]) -> list[str]:
    lines = ["## Total de voos por ano", ""]
    lines.append("| Ano | Governo | Voos | FDS | FDS% | Noturnos |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for ano, voos in por_ano.items():
        gov = governo_de(ano)
        fds = sum(1 for v in voos if v["decolagem"].weekday() >= 5)
        not_ = sum(1 for v in voos if v["decolagem"].hour >= 22 or v["decolagem"].hour < 5)
        lines.append(
            f"| {ano} | {gov} | {len(voos)} | {fds} | {_pct(fds, len(voos))} | {not_} |"
        )
    return lines + [""]


def secao_comparativo_governo(por_ano: dict[int, list]) -> list[str]:
    grupos: dict[str, list] = defaultdict(list)
    for ano, voos in por_ano.items():
        grupos[governo_de(ano)].extend(voos)

    lines = ["## Comparativo por governo", ""]
    linhas_gov = []
    for gov, (ini, fim) in GOVERNOS.items():
        voos = grupos.get(gov, [])
        if not voos:
            continue
        fim_real = min(fim, datetime.now().year)
        periodo = f"{ini}–{fim_real}"
        fds = sum(1 for v in voos if v["decolagem"].weekday() >= 5)
        not_ = sum(1 for v in voos if v["decolagem"].hour >= 22 or v["decolagem"].hour < 5)
        top3 = Counter(v["autoridade"] for v in voos).most_common(3)
        top3_str = "; ".join(f"{a.split()[-1]} ({n})" for a, n in top3)
        linhas_gov.append((gov, periodo, voos, fds, not_, top3_str))

    lines.append("| Governo | Anos | Total voos | FDS | Noturnos | Top 3 autoridades |")
    lines.append("|---|---|---:|---:|---:|---|")
    for gov, periodo, voos, fds, not_, top3_str in linhas_gov:
        lines.append(f"| {gov} | {periodo} | {len(voos)} | {fds} | {not_} | {top3_str} |")
    return lines + [""]


def secao_top_autoridades(por_ano: dict[int, list], n: int = 20) -> list[str]:
    todos = [v for voos in por_ano.values() for v in voos]
    cnt = Counter(v["autoridade"] for v in todos)
    lines = [f"## Top {n} autoridades (histórico completo)", ""]
    lines.append("| # | Autoridade | Total | Bolsonaro | Lula 3 |")
    lines.append("|---|---|---:|---:|---:|")
    for i, (aut, total) in enumerate(cnt.most_common(n), 1):
        por_gov: dict[str, int] = defaultdict(int)
        for ano, voos in por_ano.items():
            for v in voos:
                if v["autoridade"] == aut:
                    por_gov[governo_de(ano)] += 1
        b = por_gov.get("Bolsonaro", 0)
        l = por_gov.get("Lula 3", 0)
        lines.append(f"| {i} | {aut} | {total} | {b} | {l} |")
    return lines + [""]


def secao_meses_pico(por_ano: dict[int, list], top_n: int = 10) -> list[str]:
    por_mes: Counter = Counter()
    for voos in por_ano.values():
        for v in voos:
            label = v["decolagem"].strftime("%Y-%m")
            por_mes[label] += 1

    lines = [f"## Top {top_n} meses com mais voos (picos)", ""]
    lines.append("| Mês | Voos | Governo |")
    lines.append("|---|---:|---|")
    for mes_label, n in por_mes.most_common(top_n):
        ano = int(mes_label[:4])
        lines.append(f"| {mes_label} | {n} | {governo_de(ano)} |")
    return lines + [""]


def secao_destinos_top(por_ano: dict[int, list]) -> list[str]:
    todos = [v for voos in por_ano.values() for v in voos]
    cnt = Counter(v["destino"] for v in todos)
    lines = ["## Top 20 destinos (histórico)", ""]
    lines.append("| Destino | Total |")
    lines.append("|---|---:|")
    for dest, n in cnt.most_common(20):
        lines.append(f"| {dest} | {n} |")
    return lines + [""]


def secao_autoridade_por_ano(por_ano: dict[int, list]) -> list[str]:
    """Quem mais voou em cada ano."""
    lines = ["## Campeão de voos por ano", ""]
    lines.append("| Ano | Autoridade | Voos | Governo |")
    lines.append("|---|---|---:|---|")
    for ano, voos in por_ano.items():
        if not voos:
            continue
        aut, n = Counter(v["autoridade"] for v in voos).most_common(1)[0]
        lines.append(f"| {ano} | {aut} | {n} | {governo_de(ano)} |")
    return lines + [""]


# ────────────────────────── main ──────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()

    print("Carregando CSVs...", file=sys.stderr)
    por_ano = carregar_todos()
    if not por_ano:
        print("Nenhum dado encontrado.", file=sys.stderr)
        return 1

    total_geral = sum(len(v) for v in por_ano.values())
    anos = sorted(por_ano)
    print(f"  Total: {total_geral} voos em {len(por_ano)} anos ({anos[0]}–{anos[-1]})",
          file=sys.stderr)

    linhas = [
        "# Análise Histórica — Voos de Autoridades (GABAER)",
        "",
        f"_Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
        f"Fonte: [FABdadosabertos/GABAER](https://github.com/FABdadosabertos/GABAER) · "
        f"**{total_geral} voos** de {anos[0]} a {anos[-1]}_",
        "",
    ]
    linhas += secao_totais(por_ano)
    linhas += secao_comparativo_governo(por_ano)
    linhas += secao_autoridade_por_ano(por_ano)
    linhas += secao_top_autoridades(por_ano)
    linhas += secao_meses_pico(por_ano)
    linhas += secao_destinos_top(por_ano)

    md = "\n".join(linhas)

    if args.stdout:
        print(md)
    else:
        dest = ANALISES / "historico.md"
        dest.write_text(md, encoding="utf-8")
        print(f"  → {dest.relative_to(ROOT)}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
