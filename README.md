# voos-oficiais-poc

Prova de conceito de produto jornalístico irmão do **Transparência Federal**: monitorar voos de autoridades em aeronaves da Força Aérea Brasileira (FAB), com publicação serial e base aberta.

> **Estado em 2026-05-22:** PoC virou esqueleto operacional. Dados de jan-abr/2026 ingeridos do GABAER, análise automática rodando, workflow GitHub Actions pronto pra cron diário, pedido LAI redigido. Falta: criar repo remoto, conectar Actions, enviar a LAI, esboçar edição zero pública.

---

## Por que existe

A cobertura jornalística atual sobre uso de aeronaves oficiais no Brasil é **episódica** (Lúcio Vaz, Intercept, Cláudio Humberto, Folha): cada matéria nasce e morre. Não há produto serial com (a) base aberta, (b) cruzamento sistemático voo × agenda × custo, (c) cobertura abaixo do Planalto (governos estaduais, PF, PRF).

Esse projeto vai ocupar esse espaço.

## Arquitetura — caminho escolhido (B+C)

Caminho **B**: ingestão automatizada dos CSVs mensais que o COMAER publica no repo público [FABdadosabertos/GABAER](https://github.com/FABdadosabertos/GABAER). Sem scraping web (o portal `fab.mil.br/voos` está atrás de Cloudflare Turnstile — bloqueio anti-bot que inviabiliza scraping headless de cron remoto).

Caminho **C**: pedido LAI ao COMAER para que a publicação do CSV mensal seja antecipada de D+30 para D+10. Texto em [`lai/pedido_lai_comaer.md`](lai/pedido_lai_comaer.md).

```
GABAER (GitHub)  ──[cron diário 09h UTC]──>  ingestao_gabaer.py
                                                    │
                                                    ▼
                          dados/snapshots/voos_AAAA_MM.csv
                                                    │
                                                    ▼
                                       analisar_mes.py
                                                    │
                                                    ▼
                          dados/analises/AAAA-MM.md  (commitado)
                                                    │
                                                    ▼
                          GitHub Issue automática com sumário
                                                    │
                                                    ▼
                          curadoria humana → edição da newsletter
```

Camada complementar (ADS-B/OpenSky) fica como **gatilho de furo quente** sobre o presidencial, não como base — código herdado em [`fetch_opensky.py`](fetch_opensky.py).

## Setup

```bash
cd /Users/luizlessa/voos-oficiais-poc
python3 -m venv .venv
source .venv/bin/activate
pip install playwright playwright-stealth   # opcional, só pra exploração
```

A ingestão e a análise **não exigem nenhuma dependência externa** — só stdlib Python 3.9+. O workflow no GitHub Actions usa Python 3.12 do runner.

## Uso local

```bash
# 1. Verifica e baixa CSVs novos do GABAER
python ingestao/ingestao_gabaer.py            # exit 0 sem novos, 10 com novos

# 2. Gera análise pra todos snapshots (idempotente)
python analise/analisar_mes.py --all

# Ou pra um mês específico:
python analise/analisar_mes.py dados/snapshots/voos_2026_04.csv
```

## Estrutura

```
voos-oficiais-poc/
├── ingestao/
│   └── ingestao_gabaer.py        # fetch + diff (mensais e anuais) via API GitHub
├── analise/
│   ├── analisar_mes.py           # CSV mensal → markdown com sinais jornalísticos
│   └── analisar_historico.py     # agrega 2020–hoje, comparativo por governo
├── lai/
│   └── pedido_lai_comaer.md      # texto pronto pro Fala.BR (caminho C)
├── dados/
│   ├── snapshots/                # CSVs originais (mensais + anuais) + INDEX.json
│   ├── analises/                 # AAAA-MM.md mensais + historico.md
│   ├── lookup_autoridades.json   # cargo → nome real → período (2020–2026)
│   └── custo_aeronaves.json      # custo/hora estimado por modelo + referência TCU
├── .github/workflows/
│   └── gabaer-watch.yml          # cron diário 09h UTC, abre issue se mudou
├── aeronaves.py                  # legado OpenSky — frota oficial mapeada
├── fetch_opensky.py              # legado OpenSky — fetch ADS-B
├── EDICAO_ZERO_RASCUNHO.md       # validação editorial de abril/2026
└── README.md                     # este arquivo
```

## O que a análise automática extrai

Pra cada CSV mensal, gera markdown com:

- Sumário (total, motivo Serviço/Segurança, dia da semana)
- Top 10 autoridades mais voadas
- **Concentração geográfica por autoridade** (top 3 destinos — revela base eleitoral)
- Voos em sábado/domingo
- Voos noturnos (decolagem 22h–5h)
- **Sequências do mesmo dia** (3+ pernas — tours suspeitos)
- Destinos não-capitais (interior)
- Voos "À Disposição de X" (eufemismo — passageiros sob sigilo)

Exemplo: [`dados/analises/2026-04.md`](dados/analises/2026-04.md).

## Estado atual (mai/2026)

- [x] Repo criado: https://github.com/luizlessa-dev/voos-oficiais
- [x] GitHub Actions configurado e validado (`workflow_dispatch` rodou com sucesso)
- [x] Histórico 2020–abr/2026 ingerido: **10.012 voos**
- [x] Análises mensais (jan–abr/2026) e histórica geradas
- [x] Lookup de autoridades (cargo → nome → período)
- [x] Referência de custo por hora + dados TCU
- [ ] Enviar a LAI pelo Fala.BR (preencher CPF + nº acórdão TCU TC 008.687/2024-2)
- [ ] Decidir: repo próprio ou módulo do `transparencia-v3`?

## Decisões registradas

- **Scraping de `fab.mil.br/voos` descartado** — Cloudflare Turnstile bloqueia headless, mesmo com `playwright-stealth`. Documentado em `dados/fab_voos_stealth.*`.
- **OpenSky relegado a complemento** — sem histórico anônimo, presidencial filtrado em alguns períodos, militares mascaram identidade. Vale só pra alerta pontual do FAB2101, não como base.
- **CSV mensal aceito como base** — defasagem D+25–30 é menor problema do que parecia. Valor analítico mora no padrão (cruzamento agenda × destino × custo), não no flagrante D+1.
- **Encoding misto nos CSVs históricos** — `ingestao_gabaer.py` baixa bytes brutos; `analisar_mes.py` detecta UTF-8/Latin-1.
