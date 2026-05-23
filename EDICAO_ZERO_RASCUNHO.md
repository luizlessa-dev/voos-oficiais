# Edição Zero — rascunho (recortes de abril/2026)

**Fonte:** [GABAER no GitHub](https://github.com/FABdadosabertos/GABAER), CSV oficial publicado pelo Gabinete do Comandante da Aeronáutica. 108 voos registrados em abril/2026.

> Esta é uma simulação de edição zero da newsletter, esboçada em 22/05/2026 com dados de abril, para avaliar se há material recorrente. **Não foi publicada.**

---

## 1. A rota das urnas de Hugo Motta

O presidente da Câmara, Hugo Motta (Republicanos-PB), fez **10 voos da FAB em abril**, todos classificados como "Segurança" — categoria reservada a deslocamentos da linha sucessória presidencial. **Metade tem João Pessoa ou outra cidade da Paraíba como ponta:**

- **01/04 (qua), 00h10** — Brasília → João Pessoa (madrugada)
- **04/04 (sáb), 21h** — João Pessoa → Brasília
- **22/04 (qua), 09h** — João Pessoa → Brasília
- **24/04 (qui), 07h** — Brasília → **Patos (PB)** → João Pessoa
- **26/04 (sáb), 18h** — João Pessoa → Brasília

Patos é reduto eleitoral histórico do clã Motta. A frequência semanal sugere agenda partidária na base eleitoral, financiada por aeronave da FAB sob rubrica "Segurança". A categoria existe pela linha sucessória, mas a rota é privada de qualquer presidente da Câmara que viaje pra sua base por motivo eleitoral.

**O Intercept já tocou em parte disso** em [matéria de 02/mai](https://www.intercept.com.br/2026/05/02/voo-escandaloso-hugo-motta-ciro-nogueira/). Aqui o ângulo é diferente: não um voo, **um padrão sistemático**.

---

## 2. O tour de sertão do novo ministro de Portos

Tomé Franca, que substituiu Silvio Costa Filho (saiu pra disputar o Senado por PE) no Ministério de Portos e Aeroportos, fez no **sábado 18/04** uma sequência tripla:

| Decolagem | Origem | Destino | Pax |
|---|---|---|---|
| 07h20 | Recife | Juazeiro do Norte (CE) | 7 |
| 15h10 | Juazeiro do Norte | Serra Talhada (PE) | 7 |
| 17h25 | Serra Talhada | Recife | 8 |

Em 17/04, Costa Filho havia celebrado "investimentos para aeroportos de Garanhuns, Serra Talhada e Araripina". O voo do sucessor é no **dia seguinte, sábado**, percorrendo dois redutos do sertão de PE/CE. **Pergunta:** o ministro indicado pelo antecessor que disputa o Senado por PE está fazendo agenda institucional ou cabo eleitoral?

---

## 3. O ministro que mais voou no Brasil

Alexandre Padilha (Saúde) fez **17 voos em abril** — recorde do mês. Cláudio Humberto em [coluna no Jornal da Mídia](https://www.jornaldamidia.com.br/2026/05/18/viagens-em-jatinhos-da-fab-chegam-a-400-em-2026/) registrou 18 (provável revisão do CSV). O caso mais chamativo é **23/04**, em que Padilha fez quatro pernas no mesmo dia cobrindo o eixo SP:

> Brasília → São José dos Campos → Sorocaba → Campinas → Brasília

Padilha (PT-SP) é nome frequentemente associado a disputas eleitorais em SP. Em jornada de um dia com 4 paradas em municípios paulistas, qual a divisão entre agenda do SUS e exposição política?

---

## 4. O eufemismo dos 13 voos "à disposição"

Há **13 voos** classificados como "**À Disposição do Ministro da Defesa**" em abril. Isso significa que o ministro não estava a bordo — a aeronave foi usada por terceiros sob autorização do gabinete da Defesa. O CSV não traz a lista de passageiros (sigilo de 5 anos por decisão TCU, revisto em abril/2026 para liberar a rota mas manter passageiros).

A maioria das pernas é Brasília ↔ Congonhas ↔ Santos Dumont ↔ Galeão ↔ SJC — eixo militar-industrial paulista. **Pauta:** LAI ao Ministério da Defesa pedindo identificação dos passageiros desses voos, com argumento de que a decisão TCU 2026 restringiu o sigilo à "autoridade requerente", não a aeronave em si.

---

## 5. Os números secos

- **108 voos** num único mês
- **17 voos** do ministro mais ativo (Padilha/Saúde)
- **82** classificados como "Serviço", **26** como "Segurança"
- **15 destinos** em Congonhas (SP), 4 em João Pessoa
- **11 voos** em sábado/domingo
- **Custo médio estimado** do Embraer Legacy 600 da FAB: R$ 38 mil/hora de voo *(carece confirmar com TCU 2024)*

---

## Próximas edições — pautas semente

- **Quem cabe num "À Disposição de"** — LAI sistemática
- **Os governadores que voam de FAB** — Castro/RJ, Jerônimo/BA, padrão estadual
- **Mapa dos destinos eleitorais 2026** — voos a redutos de candidatos a cargo eletivo no ano
- **A frota fantasma** — aeronaves PF/PRF que aparecem no ADS-B mas não em CSV nenhum
- **Domingo de FAB** — semestre dos voos de fim de semana

---

## Veredicto interno (não pra leitor)

**Material recorrente: SIM, com folga.**

- 108 voos/mês = 2-3 pautas viáveis por semana
- 3 pautas fortes em **um único mês** sem investigação aprofundada
- Cobertura concorrente é episódica (Lúcio Vaz, Intercept, Cláudio Humberto) — newsletter serial é território vazio
- Custo de produção: ~2-3h/semana (scraping diário automatizado + curadoria editorial)

**Risco do método:** o CSV é mensal (publicação ao fim do mês). Em D+30 a "novidade" esfria. **Solução:** scraping diário do portal [fab.mil.br/voos](https://www.fab.mil.br/voos) (que publica em D+1) para o sinal quente, GABAER mensal para análise histórica/agregada.

**Próximo passo recomendado:** montar o scraper do portal D+1 (precisa contornar 403 do Cloudflare — provável necessidade de browser headless) + cron diário no GitHub Actions, sem custo recorrente.
