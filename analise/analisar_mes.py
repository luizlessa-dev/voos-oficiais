"""
Análise mensal automática de um CSV GABAER.

Recebe o caminho de um CSV em dados/snapshots/voos_AAAA_MM.csv e gera
um relatório markdown em dados/analises/AAAA-MM.md com:

- Sumário (total, por motivo, por dia da semana)
- Top 10 autoridades mais voadas
- Voos em fim de semana
- Voos noturnos (decolagem 22h-5h)
- Sequências do mesmo dia (3+ pernas)
- Destinos não-capitais
- Voos "À Disposição de" (eufemismo opaco)
- Concentração geográfica por autoridade (top 3 destinos de cada)

Uso:
    python analisar_mes.py dados/snapshots/voos_2026_04.csv
    python analisar_mes.py --all   # gera análise pra todos os snapshots
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
SNAPSHOTS  = ROOT / "dados" / "snapshots"
ANALISES   = ROOT / "dados" / "analises"
NEWSLETTER = ROOT / "dados" / "newsletter"
ANALISES.mkdir(parents=True, exist_ok=True)
NEWSLETTER.mkdir(parents=True, exist_ok=True)

DIAS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
DIA_CURTO = ["seg", "ter", "qua", "qui", "sex", "SÁB", "DOM"]

# Parentéticos que identificam aeroportos/aeródromos brasileiros.
# Qualquer outro parentético em destino/origem é tratado como país = voo internacional.
AEROPORTOS_BR_PAREN = {
    "congonhas", "santos dumont", "pampulha", "galeão", "guarulhos",
    "ponta pelada", "eduardo gomes", "parnamirim", "afonsos", "confins",
    "arealva", "santa cruz",
}

_RE_PAREN = re.compile(r"\(([^)]+)\)")


def is_internacional(local: str) -> bool:
    """Retorna True se o destino/origem tem parentético que NÃO é aeroporto brasileiro."""
    m = _RE_PAREN.search(local)
    if not m:
        return False
    return m.group(1).strip().lower() not in AEROPORTOS_BR_PAREN


# Conjunto considerado "capital grande" — pra destacar destinos atípicos.
# Todas as 27 capitais estaduais/DF + variantes de aeroporto que aparecem nos CSVs.
# Destinos FORA desse conjunto são considerados "não-capitais" (interior).
CAPITAIS_ESTADUAIS = {
    # Distrito Federal
    "Brasília",
    # Acre
    "Rio Branco",
    # Alagoas
    "Maceió",
    # Amapá
    "Macapá",
    # Amazonas
    "Manaus", "Manaus (Eduardo Gomes)", "Manaus (Ponta Pelada)",
    # Bahia
    "Salvador", "Salvador (Deputado Luís Eduardo Magalhães)",
    # Ceará
    "Fortaleza",
    # Espírito Santo
    "Vitória",
    # Goiás
    "Goiânia",
    # Maranhão
    "São Luís",
    # Mato Grosso
    "Cuiabá",
    # Mato Grosso do Sul
    "Campo Grande",
    # Minas Gerais
    "Belo Horizonte", "Belo Horizonte (Pampulha)", "Belo Horizonte (Confins)",
    # Pará
    "Belém",
    # Paraíba
    "João Pessoa",
    # Paraná
    "Curitiba", "Curitiba (Afonso Pena)",
    # Pernambuco
    "Recife",
    # Piauí
    "Teresina",
    # Rio de Janeiro
    "Rio de Janeiro", "Rio de Janeiro (Santos Dumont)", "Rio de Janeiro (Galeão)",
    # Rio Grande do Norte
    "Natal", "Natal (Augusto Severo)",
    # Rio Grande do Sul
    "Porto Alegre", "Porto Alegre (Salgado Filho)",
    # Rondônia
    "Porto Velho",
    # Roraima
    "Boa Vista",
    # Santa Catarina
    "Florianópolis",
    # São Paulo
    "São Paulo", "São Paulo (Congonhas)", "São Paulo (Guarulhos)",
    # Sergipe
    "Aracaju",
    # Tocantins
    "Palmas",
}
# Mantém nome legado para não quebrar referências externas
CAPITAIS_GRANDES = CAPITAIS_ESTADUAIS


def _detectar_encoding(path: Path) -> str:
    """Tenta UTF-8; cai pra latin-1 se quebrar (alguns CSVs antigos GABAER)."""
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
        header = next(reader)
        for row in reader:
            if not row or not row[0].strip():
                continue
            try:
                dec_raw = row[2].strip()
                pou_raw = row[4].strip()
                dec_dt = datetime.strptime(dec_raw, "%d/%m/%Y - %H:%M")
                try:
                    pou_dt = datetime.strptime(pou_raw, "%d/%m/%Y - %H:%M")
                except ValueError:
                    pou_dt = None
            except (ValueError, IndexError):
                continue
            voos.append({
                "autoridade": row[0].strip(),
                "origem": row[1].strip(),
                "decolagem": dec_dt,
                "destino": row[3].strip(),
                "pouso": pou_dt,
                "motivo": row[5].strip() if len(row) > 5 else "",
                "passageiros": row[6].strip() if len(row) > 6 else "",
            })
    return voos


def fmt_dt(dt: datetime) -> str:
    return dt.strftime("%d/%m %H:%M")


def secao_sumario(voos: list[dict], ano: int, mes: int) -> list[str]:
    lines = ["## Sumário", ""]
    lines.append(f"- **Total de voos:** {len(voos)}")
    motivos = Counter(v["motivo"] for v in voos)
    motivo_str = ", ".join(f"{n} {m}" for m, n in motivos.most_common())
    lines.append(f"- **Por motivo:** {motivo_str}")
    dias = Counter(v["decolagem"].weekday() for v in voos)
    dias_str = ", ".join(
        f"{DIA_CURTO[d]} {dias.get(d, 0)}" for d in range(7)
    )
    lines.append(f"- **Por dia da semana:** {dias_str}")
    fds = sum(1 for v in voos if v["decolagem"].weekday() >= 5)
    lines.append(f"- **Voos em sábado/domingo:** {fds} ({fds/len(voos)*100:.1f}%)")
    return lines + [""]


def secao_top_autoridades(voos: list[dict]) -> list[str]:
    cnt = Counter(v["autoridade"] for v in voos)
    lines = ["## Top 10 autoridades mais voadas", ""]
    lines.append("| # | Autoridade | Voos |")
    lines.append("|---|---|---:|")
    for i, (a, n) in enumerate(cnt.most_common(10), 1):
        lines.append(f"| {i} | {a} | {n} |")
    return lines + [""]


def secao_fim_de_semana(voos: list[dict]) -> list[str]:
    fds = sorted(
        [v for v in voos if v["decolagem"].weekday() >= 5],
        key=lambda v: v["decolagem"],
    )
    if not fds:
        return []
    lines = [f"## Voos em fim de semana ({len(fds)})", ""]
    lines.append("| Dia | Decolagem | Autoridade | Rota | Motivo |")
    lines.append("|---|---|---|---|---|")
    for v in fds:
        dia = DIA_CURTO[v["decolagem"].weekday()]
        lines.append(
            f"| {dia} | {fmt_dt(v['decolagem'])} "
            f"| {v['autoridade']} | {v['origem']} → {v['destino']} | {v['motivo']} |"
        )
    return lines + [""]


def secao_noturnos(voos: list[dict]) -> list[str]:
    notu = [v for v in voos if v["decolagem"].hour >= 22 or v["decolagem"].hour < 5]
    if not notu:
        return []
    lines = [f"## Voos noturnos — decolagem 22h–5h ({len(notu)})", ""]
    lines.append("| Decolagem | Autoridade | Rota | Motivo |")
    lines.append("|---|---|---|---|")
    for v in sorted(notu, key=lambda v: v["decolagem"]):
        lines.append(
            f"| {fmt_dt(v['decolagem'])} | {v['autoridade']} "
            f"| {v['origem']} → {v['destino']} | {v['motivo']} |"
        )
    return lines + [""]


def secao_sequencias(voos: list[dict]) -> list[str]:
    """Pra cada (autoridade, dia), se houver 3+ pernas, lista a sequência."""
    bucket: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for v in voos:
        chave = (v["autoridade"], v["decolagem"].strftime("%Y-%m-%d"))
        bucket[chave].append(v)
    seqs = [(k, vs) for k, vs in bucket.items() if len(vs) >= 3]
    if not seqs:
        return []
    seqs.sort(key=lambda kv: (-len(kv[1]), kv[0]))
    lines = [f"## Sequências do mesmo dia (3+ pernas) — {len(seqs)} ocorrências", ""]
    for (autor, dia), vs in seqs:
        vs = sorted(vs, key=lambda v: v["decolagem"])
        lines.append(f"### {autor} — {dia}")
        for v in vs:
            lines.append(
                f"- {fmt_dt(v['decolagem'])}  {v['origem']} → {v['destino']} "
                f"({v['motivo']}, {v['passageiros']} pax)"
            )
        lines.append("")
    return lines


def secao_destinos_atipicos(voos: list[dict]) -> list[str]:
    cnt = Counter(
        v["destino"] for v in voos
        if v["destino"] not in CAPITAIS_GRANDES
    )
    if not cnt:
        return []
    lines = ["## Destinos não-capitais (top 15)", ""]
    lines.append("| Destino | Voos |")
    lines.append("|---|---:|")
    for d, n in cnt.most_common(15):
        lines.append(f"| {d} | {n} |")
    return lines + [""]


def secao_a_disposicao(voos: list[dict]) -> list[str]:
    ads = [v for v in voos if v["autoridade"].lower().startswith("à disposição")
           or v["autoridade"].lower().startswith("a disposição")]
    if not ads:
        return []
    lines = [f"## Voos 'À Disposição de X' ({len(ads)})", ""]
    lines.append(
        "_Categoria opaca: aeronave usada por terceiros sob autorização "
        "do gabinete. Passageiros não constam no CSV (sigilo TCU)._"
    )
    lines.append("")
    cnt_por_autor = Counter(v["autoridade"] for v in ads)
    for autor, n in cnt_por_autor.most_common():
        lines.append(f"### {autor} ({n} voos)")
        for v in sorted([x for x in ads if x["autoridade"] == autor],
                        key=lambda v: v["decolagem"]):
            lines.append(
                f"- {fmt_dt(v['decolagem'])}  {v['origem']} → {v['destino']}"
            )
        lines.append("")
    return lines


def secao_internacionais(voos: list[dict]) -> list[str]:
    """Voos com origem ou destino fora do Brasil."""
    intl = [
        v for v in voos
        if is_internacional(v["destino"]) or is_internacional(v["origem"])
    ]
    if not intl:
        return []

    # Extrai país do parentético
    def pais(local: str) -> str:
        m = _RE_PAREN.search(local)
        return m.group(1).strip() if m else local

    paises = Counter(
        pais(v["destino"]) if is_internacional(v["destino"]) else pais(v["origem"])
        for v in intl
    )

    lines = [f"## Voos internacionais ({len(intl)})", ""]
    lines.append(
        "_Origem ou destino fora do território brasileiro. "
        "Custo estimado tipicamente 3–10× maior que o voo doméstico equivalente._"
    )
    lines.append("")

    # Top países
    lines.append("**Países visitados:** " +
                 ", ".join(f"{p} ({n})" for p, n in paises.most_common()))
    lines.append("")

    lines.append("| Decolagem | Autoridade | Rota | Pax | Motivo |")
    lines.append("|---|---|---|---:|---|")
    for v in sorted(intl, key=lambda v: v["decolagem"]):
        lines.append(
            f"| {fmt_dt(v['decolagem'])} | {v['autoridade']} "
            f"| {v['origem']} → {v['destino']} "
            f"| {v['passageiros']} | {v['motivo']} |"
        )
    return lines + [""]


def secao_concentracao(voos: list[dict]) -> list[str]:
    """Top 3 destinos por autoridade — revela viés geográfico."""
    por_autor: dict[str, Counter] = defaultdict(Counter)
    cnt_total = Counter()
    for v in voos:
        if v["autoridade"].lower().startswith(("à disposição", "a disposição")):
            continue
        por_autor[v["autoridade"]][v["destino"]] += 1
        cnt_total[v["autoridade"]] += 1
    # só autoridades com 3+ voos
    relevantes = [(a, n) for a, n in cnt_total.most_common() if n >= 3]
    if not relevantes:
        return []
    lines = ["## Concentração geográfica por autoridade", ""]
    lines.append("_Top 3 destinos de cada autoridade com 3+ voos. "
                 "Repetições puxam pauta (base eleitoral, evento, lobby)._")
    lines.append("")
    lines.append("| Autoridade | Total | Destinos mais frequentes |")
    lines.append("|---|---:|---|")
    for autor, total in relevantes:
        top = por_autor[autor].most_common(3)
        top_str = "; ".join(f"{d} ({n})" for d, n in top)
        lines.append(f"| {autor} | {total} | {top_str} |")
    return lines + [""]


MESES_NOME = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
              "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def gerar_newsletter(voos: list[dict], ano: int, mes: int) -> Path:
    """Rascunho editorial pronto para colar no Beehiiv. Uso interno — não publicado."""
    fds  = [v for v in voos if v["decolagem"].weekday() >= 5]
    notu = [v for v in voos if v["decolagem"].hour >= 22 or v["decolagem"].hour < 5]

    bucket: dict[tuple, list] = defaultdict(list)
    for v in voos:
        bucket[(v["autoridade"], v["decolagem"].strftime("%Y-%m-%d"))].append(v)
    seqs = [(k, vs) for k, vs in bucket.items() if len(vs) >= 3]

    top3 = Counter(v["autoridade"] for v in voos).most_common(3)

    mes_ext = MESES_NOME[mes]
    titulo  = f"Radar FAB — {mes_ext} {ano}"

    lines = [
        f"# {titulo}",
        "",
        f"> **Edição {mes_ext} {ano}** · {len(voos)} voos registrados · "
        f"Fonte: GABAER/COMAER · Decreto 10.267/2020",
        "",
        "---",
        "",
        "## ✏️ Lead (preencher manualmente)",
        "",
        "_[2–3 frases contextualizando o mês: algum evento político relevante, "
        "agenda presidencial, crise ministerial? Cole aqui antes de enviar.]_",
        "",
        "---",
        "",
        "## Os números do mês",
        "",
        f"- **{len(voos)} voos** de autoridades em aeronaves da FAB",
        f"- **{len(fds)} voos em fim de semana** ({len(fds)/len(voos)*100:.0f}% do total)",
        f"- **{len(notu)} voos noturnos** (decolagem entre 22h e 5h)",
        f"- **{len(seqs)} sequências** de 3+ pernas no mesmo dia",
        "",
        "### Quem mais voou",
        "",
    ]

    for i, (aut, n) in enumerate(top3, 1):
        lines.append(f"{i}. **{aut}** — {n} voos")
    lines.append("")

    # Destaque editorial: fim de semana
    if fds:
        lines += [
            "---",
            "",
            "## Destaque: voos de fim de semana",
            "",
            "_Os voos abaixo ocorreram em sábados ou domingos. "
            "Verifique se coincidem com eventos políticos ou agendas públicas declaradas._",
            "",
            "| Data | Autoridade | Rota | Motivo |",
            "|---|---|---|---|",
        ]
        for v in sorted(fds, key=lambda v: v["decolagem"])[:10]:
            dia = DIA_CURTO[v["decolagem"].weekday()]
            lines.append(
                f"| {dia} {fmt_dt(v['decolagem'])} | {v['autoridade']} "
                f"| {v['origem']} → {v['destino']} | {v['motivo']} |"
            )
        if len(fds) > 10:
            lines.append(f"_... e mais {len(fds) - 10} voos. Ver análise completa._")
        lines.append("")

    # Destaque editorial: sequências
    if seqs:
        seqs.sort(key=lambda kv: (-len(kv[1]), kv[0]))
        lines += [
            "---",
            "",
            f"## Destaque: tours em um dia ({len(seqs)} ocorrências)",
            "",
            "_Sequências de 3+ pernas no mesmo dia podem indicar "
            "campanha política disfarçada de agenda oficial._",
            "",
        ]
        for (autor, dia), vs in seqs[:3]:
            vs = sorted(vs, key=lambda v: v["decolagem"])
            lines.append(f"**{autor} — {dia}**")
            for v in vs:
                lines.append(
                    f"- {fmt_dt(v['decolagem'])}  {v['origem']} → {v['destino']}"
                )
            lines.append("")

    lines += [
        "---",
        "",
        f"_Radar FAB · radar.transparenciafederal.com · "
        f"Dados: GABAER/COMAER · gerado em {datetime.now().strftime('%Y-%m-%d')}_",
    ]

    out = NEWSLETTER / f"{ano:04d}-{mes:02d}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"  → {out.relative_to(ROOT)} (newsletter)", file=sys.stderr)
    return out


def gerar_analise(csv_path: Path) -> Path:
    nome = csv_path.stem  # voos_2026_04 ou voos_2025_anual
    partes = nome.split("_")
    if len(partes) != 3 or not partes[2].isdigit():
        print(f"  Ignorando arquivo anual em analisar_mes.py: {csv_path.name}", file=sys.stderr)
        return None
    _, ano_s, mes_s = partes
    ano, mes = int(ano_s), int(mes_s)

    voos = parse_csv(csv_path)
    if not voos:
        print(f"  Nenhum voo válido em {csv_path}", file=sys.stderr)
        return None

    out = ANALISES / f"{ano:04d}-{mes:02d}.md"
    mes_nome = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                "Jul", "Ago", "Set", "Out", "Nov", "Dez"][mes]

    lines = [
        f"# Voos de Autoridades — {mes_nome}/{ano}",
        "",
        f"_Análise automatizada gerada em {datetime.now().strftime('%Y-%m-%d %H:%M')}. "
        f"Fonte: [GABAER](https://github.com/FABdadosabertos/GABAER), "
        f"Decreto 10.267/2020. Total: {len(voos)} voos._",
        "",
    ]
    lines += secao_sumario(voos, ano, mes)
    lines += secao_top_autoridades(voos)
    lines += secao_concentracao(voos)
    lines += secao_internacionais(voos)
    lines += secao_fim_de_semana(voos)
    lines += secao_noturnos(voos)
    lines += secao_sequencias(voos)
    lines += secao_destinos_atipicos(voos)
    lines += secao_a_disposicao(voos)

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"  → {out.relative_to(ROOT)}", file=sys.stderr)
    gerar_newsletter(voos, ano, mes)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", help="caminho de um CSV em dados/snapshots/")
    ap.add_argument("--all", action="store_true", help="processa todos snapshots")
    args = ap.parse_args()

    if args.all:
        for p in sorted(SNAPSHOTS.glob("voos_*.csv")):
            print(f"Analisando {p.name}...", file=sys.stderr)
            gerar_analise(p)
        return 0

    if not args.csv:
        ap.print_help()
        return 2

    p = Path(args.csv)
    if not p.exists():
        print(f"Arquivo não encontrado: {p}", file=sys.stderr)
        return 1
    gerar_analise(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
