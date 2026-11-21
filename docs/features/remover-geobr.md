# Feature: Remover o geobr (Ipea) do projeto

- **Status**: Concluído
- **Data**: 2026-11-19
- **Componentes**: `scripts/commands/escolas_dados__cruzar_inep_cnefe.py`,
  `scripts/commands/ipea_geobr_escolas__baixar_dados.py` (removido), docs e páginas web que citam o geobr

## Objetivo

O ponto do INEP de cada escola passa a vir **só** da exportação manual do
Catálogo de Escolas do painel do INEP Data (`data/inep_catalogo_escolas.csv`).
O geobr (Ipea), que redistribuía o cadastro de 2023 e servia de reserva,
sai do projeto.

## Motivação

- A exportação do INEP Data é a fonte primária e é o que o público em geral
  tem à mão; o geobr só redistribui o mesmo cadastro (mesmo ponto em 100% das
  155.232 escolas presentes nas duas bases, doc 09).
- A exportação traz o endereço (`Endereço`, preenchido nas 210.320 escolas),
  que era o argumento para usar o geobr 2.x no Censo 2025.
- Menos peças: sem GeoPackage de 97 MB, sem script de download, sem
  `geopandas` no ETL e sem a coluna `INEP_ORIGEM_PONTO`.

## Custo aceito

As 1.007 escolas do Censo 2024 (AM, PA, SP; 201 em funcionamento em 2024)
que só tinham ponto do INEP pelo geobr perdem esse ponto. São escolas que
saíram do cadastro atual do INEP. Seguem com o ponto do CNEFE quando o
casamento acha a escola, ou ficam sem coordenada.

## Tarefas

| # | Tarefa | Justificativa | Status |
|---|--------|---------------|--------|
| 1 | Tirar a reserva do geobr do ETL | É a única parte do código que lê o geobr. | Feito |
| 2 | Remover a coluna `INEP_ORIGEM_PONTO` | Com uma fonte só, a coluna teria um valor único e não informa nada. | Feito |
| 3 | Apagar `ipea_geobr_escolas__baixar_dados.py` | Sem consumidor, o script só confunde quem for reproduzir o pipeline. | Feito |
| 4 | Rodar o ETL e comparar com a saída anterior | Medir o efeito real da remoção (escolas que mudam de status ou perdem ponto). | Feito |
| 5 | Atualizar textos (docs, `.gitignore`, páginas web, exemplos) | A documentação não pode mandar baixar ou citar uma fonte que o projeto não usa mais. Nos docs 08 e 09 a história fica, marcada como substituída. | Feito |
| 6 | Apagar `data/ipea_geobr_escolas/` | Libera 97 MB; o arquivo não está no git. | Feito |

## O que foi feito

### Tarefas 1 e 2: ETL sem o geobr e sem `INEP_ORIGEM_PONTO`

- `scripts/commands/escolas_dados__cruzar_inep_cnefe.py`: removidos
  `ARQUIVO_INEP_GEOBR`, `ORIGEM_CATALOGO`, `ORIGEM_GEOBR`, o bloco da reserva
  (leitura do GeoPackage com `geopandas`) e a coluna `INEP_ORIGEM_PONTO`
  (saída principal e auditoria). `carregar_coordenadas_inep` recebe só o
  caminho da exportação; as coordenadas passam a ser `(lat, lon, escolas_no_ponto)`.
- Docstring do módulo atualizada.

### Tarefa 3: script de download apagado

- `git rm scripts/commands/ipea_geobr_escolas__baixar_dados.py`.

### Tarefa 4: ETL rodado e comparado

```sh
.venv/bin/python scripts/commands/escolas_dados__cruzar_inep_cnefe.py   # AM, PA, SP (3 min)
.venv/bin/python scripts/commands/escolas_mapa__gerar_dados_web.py
.venv/bin/python scripts/commands/escolas_mapa__gerar_dados_auditoria.py
```

Comparação com a saída anterior (cópia guardada antes da mudança), por `CO_ENTIDADE`:

| Medida | Antes | Depois |
|--------|------:|-------:|
| Escolas | 51.892 | 51.892 |
| Com ponto do INEP | 42.508 | 41.501 |
| Sem coordenada final | 6.320 | 6.903 |

As 1.007 escolas da reserva (SP 726, PA 246, AM 35):

| Status antes → depois | Escolas |
|-----------------------|--------:|
| `inep_sem_cnefe` → `sem_correspondencia` | 583 |
| `endereco_exato` → `endereco_exato` (mesma coordenada) | 297 |
| `cep_numero` → `cep_numero` (mesma coordenada) | 26 |
| `inep_*` → `nome_ajustado` | 74 |
| `inep_*` → `cep_numero` | 17 |
| `inep_*` → `nome_exato` | 10 |

- Das 201 em funcionamento em 2024: 92 ficaram sem coordenada, 76
  `endereco_exato`, 17 `cep_numero`, 12 `nome_ajustado`, 4 `nome_exato`.
- Fora da reserva, só 3 escolas mudaram, e só em `INEP_ESCOLAS_NO_PONTO`
  (2 → 1): dividiam o ponto com uma escola que só estava no geobr. Nenhum
  status mudou.

### Tarefa 5: textos atualizados

- `.gitignore`: removida a entrada de `data/ipea_geobr_escolas/`.
- `scripts/utils/previsualizar_dados.py`: removido o exemplo com o GeoPackage.
- `scripts/commands/inep_cadastro_escolar__juntar_exportacoes.py`: docstring sem o geobr.
- `web/escolas_auditoria.html`, `web/js/escolas_auditoria.js`: a origem do
  ponto do INEP passa a ser "exportação do painel do INEP Data".
- `web/index.html`: removida a etiqueta `geobr` dos dois cards.
- Docs 05 e 06: nota datada de que o ponto vem da exportação.
- Doc 08: nota no topo da seção do geobr (mantida como registro), comandos
  de reprodução sem o download do geobr, próximo passo 0b marcado como superado.
- Doc 09: seção do geobr 2.x e tarefas propostas marcadas como não
  adotadas; nova entrada "19/11/2026: geobr removido do projeto" com os números.
- `web/docs/*.html` regenerados com `scripts/utils/exportar_docs_org_para_html.sh`.
- `docs/features/juntar-exportacoes-catalogo-inep.md` não foi alterado: é o
  registro do que foi feito naquela data.

### Tarefa 6: dados apagados

- `data/ipea_geobr_escolas/` (97 MB) apagado. Para tê-lo de volta seria
  preciso baixar de novo de `https://www.ipea.gov.br/geobr/data_gpkg/schools/2023/schools_2023.gpkg`.
