# Feature: Pré-visualização Visual de Conjuntos de Dados

- **Status**: Completed
- **Date**: 2026-11-19
- **Author/Agent**: AI Assistant
- **Target Components**: `scripts/commands/previsualizar_dados.py`, `docs/features/previsualizar-dados.md`
- **Document Path**: `docs/features/previsualizar-dados.md`

## 1. Goal & Overview

### 1.1 Objective
Criar um script CLI independente (`scripts/commands/previsualizar_dados.py`) capaz de inspecionar apenas o esquema e um número limitado de linhas de qualquer conjunto de dados do projeto (CSV/TSV solto, CSV dentro de ZIP — incluindo microdados do Censo Escolar com integração automática do dicionário `.xlsx` —, arquivos geoespaciais `.gpkg`/`.geojson`/`.shp`/`.zip` de shapefile, planilhas `.xlsx` e `.json`/`.jsonl`), gerando uma página HTML única, offline e interativa em `temp/` e abrindo-a automaticamente no navegador padrão.

### 1.2 Motivation & Value
O repositório trabalha com bases volumosas e heterogêneas (CSVs de centenas de megabytes no Censo Escolar e no CNEFE, exportações do Catálogo de Escolas do INEP com UTF-8 BOM, GeoPackages, GeoJSONs e shapefiles compactados das malhas do IBGE). Abrir arquivos inteiros em planilhas eletrônicas é lento, pode truncar linhas/códigos numéricos ou falhar com encodings/separadores variados, enquanto a visualização puramente em terminal dificulta explorar tabelas com centenas de colunas. Uma prévia visual HTML gerada a partir de leitura parcial e segura permite navegar colunas, buscar campos, filtrar valores, alternar para leitura vertical por registro e consultar descrições do dicionário sem instalar novas dependências no `.venv`.

### 1.3 Scope & Acceptance Criteria
- [x] Ler apenas N linhas (ou amostra reservatório) sem carregar bases inteiras na memória em leituras parciais e sem extrair arquivos `.zip` para o disco.
- [x] Suportar CSV/TSV (com detecção automática de encoding `utf-8-sig`/`latin-1` e separador `;`, `,`, `\t`, `|`), ZIP (CSV único, múltiplos CSVs como Censo Escolar + dicionário `.xlsx`, e Shapefile compactado), geoespaciais (`.gpkg`, `.geojson`, `.shp`, `.fgb`, `.kml`), `.xlsx` (via biblioteca padrão) e `.json`/`.jsonl`.
- [x] Resumir geometrias complexas (tipo, partes, vértices e bounding box) sem despejar coordenadas gigantes no HTML.
- [x] Gerar HTML auto-contido e offline com 3 abas interativas (`Tabela`, `Colunas (Esquema)` e `Vertical (Registros)`), busca de colunas, ocultação de colunas vazias, tema claro/escuro e proteção contra XSS.
- [x] Validar o script com `--help`, `--listar` e pré-visualizações reais de todas as categorias de datasets presentes em `data/`.

## 2. Task Breakdown & Justifications

### Task 1: Criar leitores eficientes com limite de linhas e detecção automática
- **Status**: [x] Completed
- **Justification**: Os conjuntos de dados do projeto variam de CSVs pequenos a ZIPs de 513 MB (Censo Escolar) e GeoPackages/Shapefiles com centenas de milhares de feições. Ler apenas o necessário com detecção automática de encoding (incluindo UTF-8 BOM), separador, formato dentro de ZIP e resumo seguro de geometrias evita consumo excessivo de RAM/disco e elimina a necessidade de passar parâmetros manuais na maioria dos casos.
- **Affected Files/Components**: `scripts/commands/previsualizar_dados.py`
- **What Was Done**:
  - Criado `scripts/commands/previsualizar_dados.py` com leitura parcial para CSV/TSV (`nrows`, `skiprows`, amostragem reservatório com min-heap em blocos de `50.000` linhas), ZIP (detecção de shapefile compactado, CSV único automático, multi-tabela com `--tabela`, e leitura do dicionário `.xlsx` do INEP via `"dicion" in Path(n).name.lower()`), geoespaciais via `pyogrio` + `shapely` com importação preguiçosa e resumo de geometrias (`POINT` e `MultiPolygon/Polygon/LineString` com partes, vértices e `bbox`), Excel `.xlsx` via `zipfile` + `xml.etree.ElementTree.iterparse` (sem `openpyxl`), e JSON/JSONL/GeoJSON.
  - Implementada detecção automática de encoding (`utf-8-sig` para remover BOM UTF-8 / `latin-1`) e pontuação de separadores (`;`, `,`, `\t`, `|`).

### Task 2: Implementar cálculo de metadados e perfil resumido por coluna sobre as linhas carregadas
- **Status**: [x] Completed
- **Justification**: Antes de manipular ou cruzar uma base, é preciso enxergar rapidamente preenchimento, cardinalidade na amostra, tipo aparente (diferenciando códigos com zero à esquerda de inteiros puros), valores mais frequentes/exemplos e o significado oficial das variáveis codificadas quando houver dicionário do INEP.
- **Affected Files/Components**: `scripts/commands/previsualizar_dados.py`
- **What Was Done**:
  - Implementado `analisar_colunas()` calculando preenchidas, vazias, `% preenchidas`, distintos, até 5 exemplos únicos, top 5 valores mais frequentes, inferência de tipo (`geometria`, `vazia`, `booleano`, `inteiro` sem zero à esquerda, `decimal`, `data`, `texto`) e enriquecimento com descrição, tipo, tamanho e categorias do dicionário INEP (priorizando a aba correspondente à tabela selecionada).

### Task 3: Construir gerador de HTML auto-contido e offline com interface interativa em 3 abas
- **Status**: [x] Completed
- **Justification**: Bases largas (como `Tabela_Escola` com 290+ colunas) ficam ilegíveis em uma grade horizontal simples. Uma interface HTML única sem dependências de CDN oferece seleção dinâmica de colunas na barra lateral, busca global e ordenação na aba `Tabela`, inspeção de esquema na aba `Colunas` e leitura registro-a-registro na aba `Vertical`, mantendo segurança contra quebra de `<script>` e XSS.
- **Affected Files/Components**: `scripts/commands/previsualizar_dados.py`
- **What Was Done**:
  - Implementado `TEMPLATE_HTML` e `gerar_html()` 100% offline (HTML5/CSS3/ES6 puro), com tema claro/escuro, 3 abas (`Tabela`, `Colunas (Esquema)` e `Vertical (Registros)`), painel lateral recolhível de seleção/busca de colunas, ocultação de colunas vazias, rótulos do dicionário INEP inline, cópia de colunas visíveis, modal de inspeção de célula, renderização DOM segura via `document.createElement` + `textContent`, substituição em passagem única (`re.sub`) e escape JSON RFC 8259 de `<` para `\u003c` (mais `\u2028`/`\u2029`).

### Task 4: Montar interface CLI, saída em `temp/`, `--listar` e abertura no navegador
- **Status**: [x] Completed
- **Justification**: Um CLI ergonômico (`argparse`) alinhado às convenções do projeto (`scripts/commands/`) permite descobrir tabelas/camadas/abas disponíveis (`--listar`), limitar linhas (`-n`), saltar registros (`--pular`), amostrar (`--amostra`), filtrar colunas (`--colunas`, `--filtro-colunas`), salvar em `temp/` (já ignorado pelo `.gitignore`) e abrir no navegador via URI `file://` (ou operar em modo headless com `--nao-abrir`).
- **Affected Files/Components**: `scripts/commands/previsualizar_dados.py`
- **What Was Done**:
  - Implementado `montar_argumentos()`, `caminho_saida_padrao()` (gravando `temp/preview_<slug>.html`) e `principal()` com resumo conciso no terminal (distinguindo `CSV:` de `Leitura:` para formatos não CSV) e abertura via `webbrowser.open(destino.resolve().as_uri())`.

### Task 5: Validar o script contra os datasets reais em `data/` e casos extremos
- **Status**: [x] Completed
- **Justification**: Testar nos arquivos reais do repositório (BOM UTF-8, ponto-e-vírgula, ZIP único do CNEFE, ZIP multi-tabela + dicionário do Censo 2025, GeoPackage, Shapefile em ZIP, GeoJSON, `.xlsx` e payload com caracteres perigosos para HTML) garante que não haja regressões, estouros de memória, HTML pesado por WKT de polígonos ou erros de parsing.
- **Affected Files/Components**: `scripts/commands/previsualizar_dados.py`, `docs/features/previsualizar-dados.md`
- **What Was Done**:
  - Executada bateria completa com `.venv/bin/python` em todos os formatos reais e casos extremos (detalhes na seção 3).
  - Durante a validação de XSS, foi identificado que escapar `<!--` como `<\!--` quebrava o parser JSON estrito (`Invalid \escape`). Corrigido em `gerar_html()` substituindo `<` por `\u003c` e usando substituição em passagem única (`re.sub`); ajustado também o rótulo de saída do terminal para `Leitura:` em formatos sem separador CSV.
  - Arquivos temporários de teste (`temp/_teste_*.html` e `/tmp/_teste_*`) removidos após validação.

## 3. Verification & Validation

Todos os comandos abaixo foram executados com `.venv/bin/python scripts/commands/previsualizar_dados.py`:

| Caso de teste | Comando / Arquivo | Resultado observado |
|---|---|---|
| `--help` | `--help` | Código 0; exibe descrição e todas as opções CLI |
| CSV UTF-8 BOM + `,` | `data/cadastroescolar_inep/Análise - Tabela da lista das escolas - Detalhado-SUL.csv -n 25 --nao-abrir` | `25 x 19`, `encoding=utf-8-sig`, `sep=','`, 67,4 KB, 0.03s; primeira coluna `Restrição de Atendimento` sem `\ufeff` |
| CSV `;` | `data/auditoria/escolas_inep_x_cnefe_2024.csv -n 30 --nao-abrir` | `30 x 37`, `encoding=utf-8-sig`, `sep=';'`, 76,0 KB, 0.03s |
| ZIP CSV único (CNEFE 266 MB) | `data/ibge_cnefe/zipfiles/13_AM.zip -n 20 --nao-abrir` | Abriu `13_AM.csv` automaticamente sem `--tabela`; `20 x 34`, 62,0 KB, 0.03s |
| ZIP multi-tabela `--listar` | `data/inep_censo_escolar/zipfiles/microdados_censo_escolar_2025.zip --listar` | Listou 6 tabelas (`curso_tecnico`, `docente`, `escola`, `gestor_escolar`, `matricula`, `turma`) + presença do dicionário `.xlsx` |
| ZIP multi-tabela sem `--tabela` | `data/inep_censo_escolar/zipfiles/microdados_censo_escolar_2025.zip --nao-abrir` | Saiu com código 1 listando as 6 tabelas e instruindo `--tabela <nome>` |
| Censo 2025 `--tabela escola` | `...microdados_censo_escolar_2025.zip --tabela escola -n 30 --nao-abrir` | `30 x 290`, `encoding=latin-1`, `sep=';'`, 290/290 cols com descrição INEP (`TP_DEPENDENCIA` mapeado com `1..4`), 236,7 KB, 0.30s |
| `--filtro-colunas` | `...microdados_censo_escolar_2025.zip -t escola --filtro-colunas INTERNET -n 10` | Filtradas 8 colunas relacionadas a `INTERNET`, 50,6 KB, 0.40s |
| GeoPackage (`.gpkg`) | `data/ipea_geobr_escolas/schools_2023.gpkg -n 20 --nao-abrir` (e `--listar`, e `--amostra -n 8 --semente 7`) | `20 / 212.313 x 20`, `CRS=EPSG:4674`, `Point` (`POINT (...)`), 65,2 KB, 0.28s (`--amostra`: 0.65s) |
| Shapefile em ZIP (`.zip`) | `data/ibge_malha_municipal/zipfiles/BR_UF_2024.zip -n 10 --nao-abrir` | `10 / 27 x 8`, `CRS=EPSG:4674`, `Polygon`, geometria resumida (`vértices \| bbox:`), 51,7 KB, 0.37s |
| GeoJSON (`.geojson`) | `data/ibge_malha_municipal/geojsonfiles/BR_uf_2024_minima.geojson -n 10 --nao-abrir` (e `--amostra -n 5 --semente 7`) | `10 / 27 x 7`, `CRS=EPSG:4326`, 51,2 KB, 0.24s (`--amostra`: 0.26s) |
| `--amostra`, `--pular`, `-n 0` | `escolas_inep_x_cnefe_2024.csv` | `--amostra -n 10 --semente 42`: `10 / 51.892` em 1.30s; `--pular 5 -n 5`: `indices_linhas == [6,7,8,9,10]` em 0.04s; `-n 0`: 0 linhas x 37 cols em 0.04s |
| `.xlsx`, `.json`, `.jsonl` | Arquivos sintéticos/extraídos em `/tmp` | `.xlsx` listou 6 abas e leu `15 x 26` em 0.05s; `.json` preservou `'001'` como `tipo='texto'`; `.jsonl --amostra` leu `2 / 3` em 0.01s |
| Segurança XSS e DOM real | Payload `</script><img src=x onerror=alert(1)>` e `"<!-- comentario -->"` + `google-chrome --headless --dump-dom` | JSON embarcado sem `<` literal e parseável via `json.loads`; DOM do Censo 2025 renderizou `table.data-grid` (`30 x 290`) e rótulos (`3 · Municipal`); DOM XSS exibiu texto escapado sem criar `<img>` |

## 4. Summary & Lessons Learned
- Entregue `scripts/commands/previsualizar_dados.py` sem adicionar nenhuma dependência ao `requirements.txt` ou ao `.venv`, atendendo CSV/TSV, ZIP (CSV único, Censo Escolar + dicionário `.xlsx`, Shapefile compactado), GeoPackage, GeoJSON, Shapefile, Excel `.xlsx` e JSON/JSONL.
- **Lição 1 (JSON dentro de `<script>`)**: escapar `<!--` com barra invertida (`<\!--`) gera JSON inválido no parser estrito; substituir `<` por `\u003c` evita qualquer fechamento prematuro de `<script>` ou comentário HTML mantendo 100% de conformidade com RFC 8259.
- **Lição 2 (Geometrias em HTML)**: resumir polígonos com quantidade de partes, vértices e bounding box mantém a prévia leve (~51 KB para `BR_UF_2024.zip`) mesmo em malhas territoriais detalhadas.
