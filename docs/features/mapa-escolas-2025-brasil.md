# Feature: Mapa de escolas do Censo 2025, Brasil inteiro

- **Status**: Concluído (falta a conferência visual no navegador)
- **Data**: 2026-11-20
- **Componentes**: `scripts/commands/escolas_mapa__gerar_dados_web.py`,
  `web/escolas_mapa_2025.html`, `web/js/escolas_mapa.js`, `web/index.html`

## Objetivo

Um mapa novo, ao lado do mapa do Censo 2024 (que não muda), com as escolas
do Censo 2025 das 27 UFs e a coordenada escolhida no casamento com o CNEFE
(`data/inep_+cnef.csv`). O mapa de auditoria de 2025 fica para uma feature
separada.

## Tarefas

| # | Tarefa | Justificativa | Status |
|---|--------|---------------|--------|
| 1 | Gerador com `--ano` (entrada, pasta de saída e caminhos do índice por ano) | Hoje o ano e a pasta são fixos: rodar sobre 2025 sobrescreveria o mapa de 2024. | Feito |
| 2 | Matrículas de 2025 (`QT_MAT_BAS`) da `Tabela_Matricula_2025`, pelo `CO_ENTIDADE` | O mapa mostra as matrículas de cada escola; em 2025 a coluna saiu da tabela de escolas. | Feito |
| 3 | JS lê de cada página qual índice carregar e o rótulo do endereço | Um JS só para os dois mapas: correções valem para ambos. Em 2025 o endereço vem do Catálogo, não do Censo. | Feito |
| 4 | Página `web/escolas_mapa_2025.html` e card em `web/index.html` | Pedido: mapa novo, sem substituir o de 2024. | Feito |
| 5 | Gerar os dados, conferir e abrir no navegador | Ver que as 27 UFs carregam e que os números batem com o CSV. | Dados conferidos; visual pendente |

## O que foi feito

### Tarefas 1 e 2: gerador

- `escolas_mapa__gerar_dados_web.py`: `--ano` (2024 padrão, 2025) escolhe a
  entrada e a pasta de saída (`POR_ANO`); o caminho de cada arquivo no
  `indice.json` sai da pasta (`web/data/escolas_2025/...`).
- `carregar_matriculas(ano)`: `CO_ENTIDADE` → `QT_MAT_BAS` da
  `Tabela_Matricula_2025_V2.csv` (178.766 escolas, código único), lida do
  ZIP; usada só quando a entrada não tem `QT_MAT_BAS`.
- Conferido: o mapa de 2024 regerado sai idêntico (`git status` limpo em
  `web/data/escolas/`).

### Tarefas 3 e 4: página

- `web/js/escolas_mapa.js`: `ESCOLAS_CONFIG` (padrão: índice de 2024 e
  rótulo "Endereço (Censo)"), sobrescrito por `window.ESCOLAS_CONFIG`.
- `web/escolas_mapa_2025.html`: cópia da página de 2024 com título de 2025,
  índice `data/escolas_2025/indice.json` e rótulo "Endereço (Catálogo de
  Escolas)".
- `web/index.html`: card "Mapa de Escolas Georreferenciadas (Censo Escolar
  2025 · Brasil)".
- README: passo 6, gerar os dados do mapa de 2025.

### Tarefa 5: dados gerados e conferidos

```sh
.venv/bin/python scripts/commands/escolas_mapa__gerar_dados_web.py --ano 2025   # 19 s
```

- `web/data/escolas_2025/`: 27 JSON + índice, 34 MB (maior: SP, 6,4 MB).
- 214.192 escolas no índice, 171.658 no mapa (= as com coordenada no CSV),
  todas com coordenada dentro do Brasil; 12.798 delas paralisadas ou
  extintas (o filtro de situação do mapa as separa).
- Matrículas: 157.523 com número, 14.135 sem (fora da Tabela_Matricula).
- Servidor local: páginas, JS e JSON respondem 200. A conferência no
  navegador não foi possível: o Chrome conectado não alcançou o
  `127.0.0.1` da máquina.
