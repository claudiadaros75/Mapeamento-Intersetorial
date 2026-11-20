# Juntar as exportações do Catálogo de Escolas do INEP

## Goal

Ter uma base única e nacional do Catálogo de Escolas do INEP, com o ponto
(latitude/longitude) do próprio INEP, a partir das exportações manuais do
painel do INEP Data (Oracle Analytics).

## Scope

- Entra: os CSVs exportados à mão em `data/cadastroescolar_inep/`, um por
  grande região (Centro-Oeste, Nordeste e Norte, Sudeste, Sul).
- Sai: `data/inep_catalogo_escolas.csv`, com as colunas originais do painel
  e mais `Arquivo de origem`.
- Também: usar esta base como fonte do ponto do INEP no ETL
  (`escolas_dados__cruzar_inep_cnefe.py`), com o geobr 2023 como reserva.

## Task Breakdown

| # | Tarefa | Justificativa | Estado |
|---|--------|---------------|--------|
| 1 | Conferir cada parte: abaixo do limite de 100.000 linhas, mesmas colunas, sem código INEP repetido | O painel corta a exportação em 100.000 linhas sem avisar (a primeira exportação, de 02/11, parou no meio de MG). Uma parte cortada deixaria escolas faltando sem que ninguém percebesse. | Feito |
| 2 | Script `scripts/commands/inep_cadastro_escolar__juntar_exportacoes.py` | A exportação é manual e vai se repetir; com um script, a junção e as conferências são sempre iguais e reproduzíveis. | Feito |
| 3 | Limpar os espaços das células | Escola sem ponto vem com Latitude/Longitude só de espaços, e não vazias; sem limpar, parece que todas têm coordenada. | Feito |
| 4 | Comparar com o geobr 2023 | Confirmar que é o mesmo ponto do INEP que o projeto já usa e medir o que a exportação nova acrescenta. | Feito |
| 5 | Pôr `data/cadastroescolar_inep/` e a base no `.gitignore` | A base tem 99 MB, quase no limite de 100 MB por arquivo do GitHub, e as partes somam 85 MB. | Feito |
| 6 | ETL: ponto do INEP vindo desta base, com o geobr 2023 como reserva | É o cadastro mais recente (escolas novas e 539 pontos a mais). A reserva é necessária: 1.007 escolas do Censo 2024 já saíram do cadastro atual e perderiam o ponto. | Feito |
| 7 | Coluna `INEP_ORIGEM_PONTO` na saída e na auditoria | Com duas fontes, é preciso saber de qual veio cada ponto para auditar. | Feito |
| 8 | Rodar o ETL de novo (AM, PA, SP) e comparar com a versão anterior | Confirmar que nenhuma escola perdeu ponto e medir o ganho. | Feito |

## What Was Done

### Tarefas 1 a 3 (19/11/2026)

- Arquivo criado: `scripts/commands/inep_cadastro_escolar__juntar_exportacoes.py`.
- Comando:
  ```sh
  .venv/bin/python scripts/commands/inep_cadastro_escolar__juntar_exportacoes.py
  ```
- Saída:
  ```
     73.586 escolas  ...Detalhado--SUDESTE.csv
     11.462 escolas  ...Detalhado-CENTRO-OESTE.csv
     97.123 escolas  ...Detalhado-NORDESTE E NORTE.csv
     28.149 escolas  ...Detalhado-SUL.csv
  Total: 210.320 escolas em 27 UFs; 155.771 com latitude/longitude
  Gravado em data/inep_catalogo_escolas.csv
  ```
- Nenhuma parte bateu no limite. A maior, Nordeste e Norte, tem 97.123 linhas,
  perto do limite: se crescer, terá de ser dividida.

### Tarefa 4 (19/11/2026)

Cruzamento pelo código INEP com `data/ipea_geobr_escolas/schools_2023.gpkg`:

| Medida | Escolas |
|--------|--------:|
| Com ponto nas duas bases | 155.232 |
| ... ponto igual (menos de 1 m) | 155.232 (100%) |
| Ponto só na exportação nova | 539 |
| Ponto só no geobr 2023 | 0 |
| Escolas só na exportação nova | 8.379 |
| Escolas só no geobr 2023 | 10.372 |

Conclusão: é o mesmo ponto do INEP. A exportação nova é um retrato mais
recente do cadastro: acrescenta 539 pontos e tem escolas novas, e deixa de
ter escolas que saíram do cadastro.

### Tarefa 5 (19/11/2026)

- Arquivo modificado: `.gitignore` (entradas `data/cadastroescolar_inep/` e
  `data/inep_catalogo_escolas.csv`).

### Tarefas 6 a 8 (19/11/2026)

- Arquivos modificados: `scripts/commands/escolas_dados__cruzar_inep_cnefe.py`
  (`carregar_coordenadas_inep` lê `data/inep_catalogo_escolas.csv` e completa
  com o geobr 2023; nova coluna `INEP_ORIGEM_PONTO`; a cópia marcada passou a
  ser `data/inep_catalogo_escolas_marcado.csv`), `docs/09-revisao-coordenadas-inep-x-cnefe.org`.
- Arquivo removido: `data/inep_catalogo_escolas_2023_marcado.csv` (substituído).
- Comando: `.venv/bin/python scripts/commands/escolas_dados__cruzar_inep_cnefe.py` (3 min).
- Resultado, comparado com o commit `df3b9f8`:

| Medida | Antes | Depois |
|--------|------:|-------:|
| Escolas (AM, PA, SP) | 51.892 | 51.892 |
| Com ponto do INEP | 42.478 | 42.508 |
| ... da exportação do INEP Data | - | 41.501 |
| ... da reserva geobr 2023 | - | 1.007 |
| Sem coordenada final | 6.336 | 6.320 |

- Mudaram de status 19 escolas: 16 `sem_correspondencia` -> `inep_sem_cnefe`,
  3 de casamento por nome -> ponto do INEP. Outras 5 mudaram só na 6ª casa
  decimal (arredondamento, ~0,1 m). Nenhuma escola perdeu ponto.
