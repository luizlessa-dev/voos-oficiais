"""
Cruzamento voo FAB × Portal da Transparência (Viagens/Diárias).

Para cada voo FAB de um ministro a um destino ESPECÍFICO (não-capital,
fora dos hubs), busca servidores do mesmo órgão que viajaram à mesma
cidade nas mesmas datas. O sinal:

COMITIVA — servidores oficiais que foram ao mesmo destino específico do
voo FAB, na mesma janela de datas. Como o GABAER registra só o número de
passageiros (anônimos), esses servidores são candidatos a ter estado a
bordo, desanonimizando parcialmente a comitiva.

LIMITAÇÃO METODOLÓGICA (importante):
- Destinos-hub (Brasília, Rio, São Paulo) são EXCLUÍDOS: co-viagem a esses
  destinos não significa nada (todo servidor viaja a Brasília o tempo todo).
- Este cruzamento NÃO prova "dupla cobrança". Não sabemos quem estava no
  voo FAB. Um servidor com passagem comercial ao mesmo destino pode ter
  ido de avião de linha, não na aeronave da FAB. O dado é um PONTO DE
  PARTIDA para apuração, não uma conclusão.

Requer variável de ambiente PORTAL_TRANSPARENCIA_API_KEY (ou --key).

Uso:
    python analise/cruzar_portal.py dados/snapshots/voos_2026_04.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT     = Path(__file__).resolve().parent.parent
ANALISES = ROOT / "dados" / "analises"
ANALISES.mkdir(parents=True, exist_ok=True)
LOOKUP   = ROOT / "dados" / "lookup_autoridades.json"

BASE = "https://api.portaldatransparencia.gov.br/api-de-dados/viagens"

# Mapa: cargo (GABAER) → código SIAFI do órgão no Portal.
# Só ministérios do Executivo aparecem no Portal (SCDP). Câmara/Senado/STF
# têm sistemas próprios e ficam de fora deste cruzamento.
CARGO_SIAFI = {
    "Ministro da Saúde":                       "36000",
    "Ministro da Educação":                    "26000",
    "Ministro da Defesa":                      "52000",
    "À Disposição do Ministro da Defesa":      "52000",
    "Ministro dos Transportes":                "39250",
    "Ministro da Justiça e Segurança Pública": "30000",
    "Ministro da Fazenda":                     "25000",
    "Ministro das Relações Exteriores":        "35000",
    "Ministro do Trabalho e Emprego":          "40000",
    "Ministro do Turismo":                     "54000",
    "Ministro das Comunicações":               "41000",
    "Ministro de Minas e Energia":             "32000",
    "Ministro da Agricultura":                 "22000",
    "Ministro do Desenvolvimento Agrário":     "55000",
    "Ministro das Cidades":                    "56000",
    "Ministro Integração do Desenvolvimento Regional": "53000",
}


# ──────────────────── normalização ────────────────────

def _norm(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower().strip()

def _so_cidade(local: str) -> str:
    """Extrai a cidade de 'São Paulo (Congonhas)' → 'sao paulo'."""
    base = local.split("(")[0].strip()
    return _norm(base)

# Destinos-hub excluídos: co-viagem a esses lugares não é sinal.
HUBS_EXCLUIDOS = {
    "brasilia", "rio de janeiro", "sao paulo",
    "belo horizonte", "salvador", "recife", "fortaleza",
    "porto alegre", "curitiba", "manaus", "belem", "goiania",
}


# ──────────────────── leitura GABAER ────────────────────

def _enc(p: Path) -> str:
    try: p.read_text(encoding="utf-8"); return "utf-8"
    except UnicodeDecodeError: return "latin-1"

def parse_csv(path: Path) -> list[dict]:
    voos = []
    with path.open(encoding=_enc(path)) as f:
        r = csv.reader(f, delimiter=";")
        next(r)
        for row in r:
            if not row or not row[0].strip(): continue
            try:
                dec = datetime.strptime(row[2].strip(), "%d/%m/%Y - %H:%M")
            except (ValueError, IndexError):
                continue
            voos.append({
                "autoridade": row[0].strip(),
                "origem": row[1].strip(),
                "decolagem": dec,
                "destino": row[3].strip() if len(row) > 3 else "",
                "passageiros": row[6].strip() if len(row) > 6 else "",
            })
    return voos


# ──────────────────── Portal ────────────────────

def portal_get(url: str, key: str) -> list:
    req = urllib.request.Request(
        url, headers={"chave-api-dados": key, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.loads(r.read())
    return d if isinstance(d, list) else []

def buscar_viagens_mes(siafi: str, ano: int, mes: int, key: str) -> list[dict]:
    """Todas as viagens de um órgão num mês (janela de afastamento)."""
    ini = f"01/{mes:02d}/{ano}"
    # último dia do mês
    if mes == 12:
        fim_dt = datetime(ano, 12, 31)
    else:
        fim_dt = datetime(ano, mes + 1, 1) - timedelta(days=1)
    fim = fim_dt.strftime("%d/%m/%Y")

    todas = []
    for pag in range(1, 21):  # até 20 páginas (300 viagens)
        params = urllib.parse.urlencode({
            "dataIdaDe": ini, "dataIdaAte": fim,
            "dataRetornoDe": ini, "dataRetornoAte": fim,
            "codigoOrgao": siafi, "pagina": pag,
        })
        try:
            lote = portal_get(f"{BASE}?{params}", key)
        except Exception as e:
            print(f"      ERRO pág {pag}: {e}", file=sys.stderr)
            break
        if not lote:
            break
        todas.extend(lote)
        if len(lote) < 15:
            break
        time.sleep(0.3)
    return todas


# ──────────────────── cruzamento ────────────────────

def cruzar(voos: list[dict], ano: int, mes: int, key: str) -> dict:
    # Voos de ministros com órgão mapeável
    voos_min = [v for v in voos if v["autoridade"] in CARGO_SIAFI]
    orgaos = sorted({CARGO_SIAFI[v["autoridade"]] for v in voos_min})

    print(f"  {len(voos_min)} voos de ministros mapeáveis · {len(orgaos)} órgãos", file=sys.stderr)

    # Busca viagens por órgão (cache por siafi)
    viagens_por_orgao: dict[str, list] = {}
    for siafi in orgaos:
        print(f"  buscando Portal órgão {siafi}...", file=sys.stderr)
        viagens_por_orgao[siafi] = buscar_viagens_mes(siafi, ano, mes, key)
        print(f"    {len(viagens_por_orgao[siafi])} viagens", file=sys.stderr)

    comitiva = []           # voo FAB a destino específico + servidor mesmo destino/data
    voos_especificos = 0    # voos a destinos não-hub
    vistos = set()          # dedup (voo, servidor)

    for v in voos_min:
        siafi = CARGO_SIAFI[v["autoridade"]]
        dest_cidade = _so_cidade(v["destino"])
        data_voo = v["decolagem"].date()

        # Pula hubs e destinos curtos/vazios
        if dest_cidade in HUBS_EXCLUIDOS or len(dest_cidade) < 5:
            continue
        voos_especificos += 1

        for viagem in viagens_por_orgao.get(siafi, []):
            motivo = _norm(viagem.get("viagem", {}).get("motivo", ""))
            ini = viagem.get("dataInicioAfastamento", "")
            fim = viagem.get("dataFimAfastamento", "")
            try:
                ini_d = datetime.strptime(ini, "%Y-%m-%d").date()
                fim_d = datetime.strptime(fim, "%Y-%m-%d").date()
            except ValueError:
                continue

            # Data do voo dentro da janela de afastamento (±1 dia)?
            if not (ini_d - timedelta(days=1) <= data_voo <= fim_d + timedelta(days=1)):
                continue

            # Destino específico do voo citado no motivo da viagem?
            if dest_cidade not in motivo:
                continue

            nome = viagem.get("beneficiario", {}).get("nome", "")
            chave = (v["decolagem"].strftime("%d/%m"), v["destino"], nome)
            if chave in vistos:
                continue
            vistos.add(chave)

            comitiva.append({
                "voo_data": v["decolagem"].strftime("%d/%m"),
                "voo_autoridade": v["autoridade"],
                "voo_destino": v["destino"],
                "voo_pax": v["passageiros"],
                "servidor": nome,
                "cargo": viagem.get("cargo", {}).get("descricao", ""),
                "passagem": viagem.get("valorTotalPassagem", 0) or 0,
                "diaria": viagem.get("valorTotalDiarias", 0) or 0,
                "afastamento": f"{ini}–{fim}",
                "motivo": viagem.get("viagem", {}).get("motivo", "")[:140],
            })

    return {"comitiva": comitiva,
            "n_voos_min": len(voos_min),
            "voos_especificos": voos_especificos,
            "orgaos": orgaos}


def gerar_md(res: dict, ano: int, mes: int) -> Path:
    comitiva = res["comitiva"]

    linhas = [
        f"# Comitiva de Voos FAB × Portal da Transparência — {ano}-{mes:02d}",
        "",
        f"_Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
        f"{res['n_voos_min']} voos de ministros · "
        f"{res['voos_especificos']} a destinos específicos · "
        f"{len(comitiva)} servidores co-viajantes identificados_",
        "",
        "> **O que isto mostra:** servidores do mesmo órgão que viajaram à mesma "
        "cidade específica (não-hub) do voo FAB, nas mesmas datas. Como o GABAER "
        "registra só o número de passageiros, esses servidores são candidatos a "
        "ter estado na comitiva.",
        ">",
        "> **O que isto NÃO prova:** que o servidor estava na aeronave da FAB. Pode "
        "ter ido de voo comercial. É ponto de partida de apuração, não conclusão. "
        "Destinos-hub (Brasília, Rio, SP) foram excluídos por gerarem ruído.",
        "",
    ]

    linhas += [f"## Servidores co-viajantes por voo ({len(comitiva)})", ""]
    if comitiva:
        por_voo = defaultdict(list)
        for r in comitiva:
            por_voo[(r["voo_data"], r["voo_autoridade"], r["voo_destino"], r["voo_pax"])].append(r)
        for (data, aut, dest, pax), gente in sorted(por_voo.items()):
            linhas.append(f"### {data} · {aut} → {dest} ({pax} passageiros no GABAER)")
            linhas.append("")
            linhas.append("| Servidor | Cargo | Diária | Passagem | Motivo |")
            linhas.append("|---|---|---:|---:|---|")
            for r in gente:
                linhas.append(
                    f"| {r['servidor'][:30]} | {r['cargo'][:22]} "
                    f"| R$ {r['diaria']:.0f} | R$ {r['passagem']:.0f} | {r['motivo'][:50]} |"
                )
            linhas.append("")
    else:
        linhas.append("_Nenhuma correspondência em destino específico neste mês._")
        linhas.append("")

    dest = ANALISES / f"portal_{ano:04d}-{mes:02d}.md"
    dest.write_text("\n".join(linhas), encoding="utf-8")
    print(f"  → {dest.relative_to(ROOT)}", file=sys.stderr)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--key", default=os.environ.get("PORTAL_TRANSPARENCIA_API_KEY", ""))
    ap.add_argument("--refazer", action="store_true", help="reprocessa meses já gerados")
    args = ap.parse_args()

    if not args.key:
        print("ERRO: defina PORTAL_TRANSPARENCIA_API_KEY ou use --key", file=sys.stderr)
        return 1

    path = Path(args.csv)
    partes = path.stem.split("_")   # voos_2025_anual  ou  voos_2026_04
    ano = int(partes[1])
    anual = (len(partes) > 2 and partes[2] == "anual")

    print(f"Lendo {path.name}...", file=sys.stderr)
    voos = parse_csv(path)
    print(f"  {len(voos)} voos", file=sys.stderr)

    if not anual:
        mes = int(partes[2])
        res = cruzar(voos, ano, mes, args.key)
        gerar_md(res, ano, mes)
        return 0

    # Arquivo anual: itera os meses presentes nos dados (pula os já gerados)
    meses = sorted({v["decolagem"].month for v in voos})
    print(f"  arquivo anual — {len(meses)} meses com voos: {meses}", file=sys.stderr)
    for mes in meses:
        alvo = ANALISES / f"portal_{ano:04d}-{mes:02d}.md"
        if alvo.exists() and not args.refazer:
            print(f"\n=== {ano}-{mes:02d} já existe — pulando (use --refazer pra forçar) ===", file=sys.stderr)
            continue
        voos_mes = [v for v in voos if v["decolagem"].month == mes]
        print(f"\n=== {ano}-{mes:02d} ({len(voos_mes)} voos) ===", file=sys.stderr)
        res = cruzar(voos_mes, ano, mes, args.key)
        gerar_md(res, ano, mes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
