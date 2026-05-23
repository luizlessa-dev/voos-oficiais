"""
Ingestão GABAER — verifica se há CSV novo ou atualizado no repo
FABdadosabertos/GABAER (pasta "Voos de Autoridades") e baixa para
dados/snapshots/voos_AAAA_MM.csv.

Mantém INDEX.json com hashes pra detectar mudanças sem re-baixar tudo.

Uso:
    python ingestao_gabaer.py            # checa e ingere o que mudou
    python ingestao_gabaer.py --force    # re-baixa todos
    python ingestao_gabaer.py --dry-run  # só mostra o que mudaria

Sai com:
    0  — sem alterações
    10 — houve CSVs novos/atualizados (lista vai pra stdout em JSON)
    1  — erro
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

REPO = "FABdadosabertos/GABAER"
PASTA = "Voos de Autoridades"
API = f"https://api.github.com/repos/{REPO}/contents/{urllib.parse.quote(PASTA)}"

# Padrão dos CSVs mensais:
#   "VOOS DE AUTORIDADES - DECRETO Nº 10.267 - ABRIL DE 2026.csv"
# Pode aparecer com N° ou Nº; mês em PT-BR.
MESES_PT = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARÇO": 3, "ABRIL": 4,
    "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
    "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}
PADRAO_MENSAL = re.compile(
    r"DECRETO\s*N[º°]\s*10\.267\s*-\s*([A-ZÇÃÉÊÍÓÔÚÂ]+)\s*DE\s*(\d{4})",
    re.IGNORECASE,
)
# CSVs anuais consolidados: "... - ANO DE 2021.csv"
PADRAO_ANUAL = re.compile(
    r"DECRETO\s*N[º°]\s*10\.267\s*-\s*ANO\s*DE\s*(\d{4})",
    re.IGNORECASE,
)

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "dados" / "snapshots"
SNAPSHOTS.mkdir(parents=True, exist_ok=True)
INDEX_PATH = SNAPSHOTS / "INDEX.json"


def _gh_get(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "voos-oficiais-ingestao/0.1",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def listar_pasta() -> list[dict]:
    raw = _gh_get(API)
    return json.loads(raw)


def parse_mes_ano(filename: str) -> Optional[tuple[int, int]]:
    """Retorna (ano, mes) para CSVs mensais, None caso contrário."""
    m = PADRAO_MENSAL.search(filename.upper())
    if not m:
        return None
    mes = MESES_PT.get(m.group(1).upper())
    if not mes:
        return None
    return (int(m.group(2)), mes)


def parse_anual(filename: str) -> Optional[int]:
    """Retorna o ano para CSVs anuais consolidados (ANO DE XXXX)."""
    m = PADRAO_ANUAL.search(filename.upper())
    return int(m.group(1)) if m else None


def carregar_index() -> dict:
    if INDEX_PATH.exists():
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return {"arquivos": {}, "ultima_checagem": None}


def salvar_index(idx: dict) -> None:
    INDEX_PATH.write_text(
        json.dumps(idx, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def baixar_csv(item: dict) -> bytes:
    # item['download_url'] aponta pro raw mas pode vir sem urlencode nos
    # espaços/caracteres especiais. Normaliza antes de baixar.
    url = item.get("download_url")
    if not url:
        raise RuntimeError(f"sem download_url para {item.get('name')}")
    # Quote apenas o path, preservando o esquema/host.
    pr = urllib.parse.urlsplit(url)
    path_seguro = urllib.parse.quote(pr.path, safe="/%")
    url = urllib.parse.urlunsplit(
        (pr.scheme, pr.netloc, path_seguro, pr.query, pr.fragment)
    )
    return _gh_get(url)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-baixa todos")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        itens = listar_pasta()
    except Exception as e:
        print(f"ERRO ao listar pasta: {e}", file=sys.stderr)
        return 1

    # Separa mensais e anuais
    csvs_mensais = []
    csvs_anuais = []
    for it in itens:
        if it.get("type") != "file" or not it["name"].lower().endswith(".csv"):
            continue
        ma = parse_mes_ano(it["name"])
        if ma is not None:
            csvs_mensais.append((ma, it))
            continue
        ano = parse_anual(it["name"])
        if ano is not None:
            csvs_anuais.append((ano, it))

    csvs_mensais.sort(key=lambda x: x[0])
    csvs_anuais.sort(key=lambda x: x[0])

    if not csvs_mensais and not csvs_anuais:
        print("Nenhum CSV encontrado.", file=sys.stderr)
        return 1

    idx = carregar_index()
    novos = []

    # ── anuais ────────────────────────────────────────────────
    for ano, item in csvs_anuais:
        nome_alvo = f"voos_{ano:04d}_anual.csv"
        path_alvo = SNAPSHOTS / nome_alvo
        sha_remoto = item.get("sha")
        registrado = idx["arquivos"].get(nome_alvo, {})

        precisa_baixar = (
            args.force
            or not path_alvo.exists()
            or registrado.get("blob_sha") != sha_remoto
        )
        if not precisa_baixar:
            continue
        if args.dry_run:
            novos.append({"arquivo": nome_alvo, "motivo": "mudou ou novo"})
            continue

        print(f"  baixando {nome_alvo}...", file=sys.stderr)
        try:
            data = baixar_csv(item)
        except Exception as e:
            print(f"  ERRO ao baixar {nome_alvo}: {e}", file=sys.stderr)
            continue

        sha256 = sha256_bytes(data)
        old_sha256 = registrado.get("sha256")
        path_alvo.write_bytes(data)
        idx["arquivos"][nome_alvo] = {
            "blob_sha": sha_remoto,
            "sha256": sha256,
            "tamanho": len(data),
            "ano": ano,
            "mes": None,
            "tipo": "anual",
            "fonte": item.get("html_url"),
        }
        novos.append({
            "arquivo": nome_alvo,
            "ano": ano,
            "mes": None,
            "tipo": "anual",
            "tamanho": len(data),
            "primeira_vez": old_sha256 is None,
            "sha256": sha256,
            "sha256_anterior": old_sha256,
        })

    # ── mensais ───────────────────────────────────────────────
    for (ano, mes), item in csvs_mensais:
        nome_alvo = f"voos_{ano:04d}_{mes:02d}.csv"
        path_alvo = SNAPSHOTS / nome_alvo
        sha_remoto = item.get("sha")
        registrado = idx["arquivos"].get(nome_alvo, {})

        precisa_baixar = (
            args.force
            or not path_alvo.exists()
            or registrado.get("blob_sha") != sha_remoto
        )

        if not precisa_baixar:
            continue

        if args.dry_run:
            novos.append({"arquivo": nome_alvo, "motivo": "mudou ou novo"})
            continue

        print(f"  baixando {nome_alvo}...", file=sys.stderr)
        try:
            data = baixar_csv(item)
        except Exception as e:
            print(f"  ERRO ao baixar {nome_alvo}: {e}", file=sys.stderr)
            continue

        sha256 = sha256_bytes(data)
        old_sha256 = registrado.get("sha256")
        path_alvo.write_bytes(data)
        idx["arquivos"][nome_alvo] = {
            "blob_sha": sha_remoto,
            "sha256": sha256,
            "tamanho": len(data),
            "ano": ano,
            "mes": mes,
            "tipo": "mensal",
            "fonte": item.get("html_url"),
        }
        novos.append({
            "arquivo": nome_alvo,
            "ano": ano,
            "mes": mes,
            "tipo": "mensal",
            "tamanho": len(data),
            "primeira_vez": old_sha256 is None,
            "sha256": sha256,
            "sha256_anterior": old_sha256,
        })

    from datetime import datetime, timezone
    idx["ultima_checagem"] = datetime.now(timezone.utc).isoformat()

    if not args.dry_run:
        salvar_index(idx)

    if novos:
        print(json.dumps({"novos": novos}, indent=2, ensure_ascii=False))
        return 10

    print(json.dumps({"novos": []}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
