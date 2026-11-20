# Feature: Mapa de auditoria do georreferenciamento, Censo 2025, Brasil inteiro

- **Status**: Concluído (falta a conferência visual no navegador)
- **Data**: 2026-11-20
- **Componentes**: `scripts/commands/escolas_mapa__gerar_dados_auditoria.py`,
  `web/escolas_auditoria_2025.html`, `web/js/escolas_auditoria.js`, `web/index.html`, `README.org`

## Objetivo

Um mapa de auditoria novo, ao lado do de 2024 (que não muda), mostrando de
onde veio a coordenada de cada escola do Censo 2025 nas 27 UFs, se o ponto
cai fora do município declarado e, quando há as duas fontes, o ponto do
INEP e o do CNEFE ligados.

## Tarefas

| # | Tarefa | Justificativa | Status |
|---|--------|---------------|--------|
| 1 | Gerador com `--ano`: entrada `data/inep_+cnef.csv`, saída `web/data/auditoria_2025/` | Hoje entrada, ano e pasta são fixos; rodar sobre 2025 sobrescreveria a auditoria de 2024. | Feito |
| 2 | Ler só as colunas usadas do `inep_+cnef.csv` e tomar `INEP_ENDERECO` do `Endereço` do Catálogo | O CSV tem 341 MB e 372 colunas; o gerador usa ~20. Em 2025 o endereço do INEP é o do Catálogo. | Feito |
| 3 | Índice: trocar `ano_cadastro_inep: "2023"` pela fonte real do ponto do INEP | Desde a remoção do geobr o ponto vem da exportação do INEP Data; "2023" está errado. | Feito |
| 4 | JS lê de cada página qual índice carregar e o rótulo do endereço | Um JS só para as duas auditorias. | Feito |
| 5 | Página `web/escolas_auditoria_2025.html`, card em `web/index.html`, passo no README | Pedido: mapa novo de auditoria; reproduzível pelo passo a passo. | Feito |
| 6 | Gerar, conferir números contra o CSV e conferir que a auditoria de 2024 não mudou | Garantir que nada se perdeu e que o mapa antigo segue igual. | Feito |

## O que foi feito

### Tarefas 1 a 3: gerador

- `escolas_mapa__gerar_dados_auditoria.py`: `--ano` (2024 padrão, 2025)
  escolhe entrada e saída (`POR_ANO`); lê só `COLUNAS_ENTRADA` + a coluna de
  endereço (`INEP_ENDERECO` em 2024, `Endereço` do Catálogo em 2025,
  renomeada para `INEP_ENDERECO`); caminho do arquivo no índice relativo a `web/`.
- Índice: `ano_cadastro_inep: "2023"` trocado por `fonte_ponto_inep`
  ("Catalogo de Escolas do INEP (exportacao do painel do INEP Data)"). O JS
  não lia esse campo.
- Auditoria de 2024 regerada: só essa linha do `indice.json` mudou.

### Tarefas 4 e 5: página

- `web/js/escolas_auditoria.js`: `AUDITORIA_CONFIG` (padrão: índice de 2024,
  rótulo "Endereço (INEP)"), sobrescrito por `window.AUDITORIA_CONFIG`.
- `web/escolas_auditoria_2025.html`: título e textos de 2025, índice
  `data/auditoria_2025/indice.json`, rótulo "Endereço (Catálogo de Escolas)".
- `web/index.html`: card da auditoria de 2025. README: passo 7.

### Tarefa 6: dados gerados e conferidos

```sh
.venv/bin/python scripts/commands/escolas_mapa__gerar_dados_auditoria.py --ano 2025   # 22 s, 2,2 GB de memória
```

- `web/data/auditoria_2025/`: 27 JSON + índice, 51 MB (maior: SP, 9,7 MB).
- 214.192 escolas no índice, 171.658 pontos (= as com coordenada no CSV).
- 71.863 escolas com o ponto da outra fonte (linha INEP × CNEFE no mapa).
- 586 pontos fora do município declarado, quase todos `inep_sem_cnefe`
  (519): ponto do INEP sem CNEFE para conferir.
- O mapa de auditoria desenha os pontos sem agrupar (canvas): com as 27 UFs
  marcadas são ~171 mil círculos, cerca de 4 vezes o volume de AM+PA+SP
  (~0,3 s por redesenho medido antes).
- Conferência visual no navegador: pendente (o Chrome conectado não alcança
  o servidor local desta máquina).
