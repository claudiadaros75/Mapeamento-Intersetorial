# Feature: Juntar o Censo Escolar 2025 ao Cadastro Escolar do INEP

- **Status**: Concluído
- **Data**: 2026-11-19
- **Componentes**: `scripts/commands/inep_censo_escolar__juntar_cadastro_escolar.py`, `.gitignore`

## Objetivo

Juntar, pelo código da escola, a tabela de escolas do Censo Escolar 2025
(microdados do INEP, `CO_ENTIDADE`) ao Catálogo de Escolas exportado do
painel do INEP Data (`data/inep_catalogo_escolas.csv`, `Código INEP`), e
gravar três CSVs:

| Arquivo | Conteúdo |
|---------|----------|
| `data/inep_censo_escolar_2025_+_cadastro_escolar_do_inep.csv` | Escolas nas duas bases: colunas do Censo + colunas do Cadastro |
| `data/inep_censo_escolar_2025_+_cadastro_escolar_do_inep__nocadastro_forado_censo.csv` | Escolas só no Cadastro |
| `data/inep_censo_escolar_2025_+_cadastro_escolar_do_inep__nocenso_forado_cadastroescolar.csv` | Escolas só no Censo |

## Motivação

Os microdados de 2025 não trazem endereço nem coordenada. O Cadastro traz
os dois (`Endereço`, `Latitude`, `Longitude`). A junção pelo código é o
primeiro passo para levar o georreferenciamento ao Censo 2025, e as duas
sobras mostram o quanto as bases divergem.

## Tarefas

| # | Tarefa | Justificativa | Status |
|---|--------|---------------|--------|
| 1 | Script que lê a tabela de escolas direto do ZIP do Censo | Não depende da pasta extraída; é o arquivo que `inep_censo_escolar__baixar_dados.py` baixa. | Feito |
| 2 | Junção pelo código, com conferência de códigos repetidos | Um código repetido em qualquer lado duplicaria linhas sem aviso. | Feito |
| 3 | Gravar as três saídas e um resumo no terminal | Os CSVs são pedidos; o resumo diz de imediato quantas escolas caem em cada um. | Feito |
| 4 | Pôr as saídas no `.gitignore` | A saída principal passa de 100 MB, o limite do GitHub. | Feito |
| 5 | Rodar e registrar os números | Confirmar que funciona e deixar a referência para comparar depois. | Feito |

## O que foi feito

### Tarefas 1 a 3: script

- Criado `scripts/commands/inep_censo_escolar__juntar_cadastro_escolar.py`.
  - Lê `Tabela_Escola_<ano>[_V2].csv` (ou `microdados_ed_basica_<ano>.csv`,
    até 2024) de dentro de `data/inep_censo_escolar/zipfiles/microdados_censo_escolar_<ano>.zip`,
    em latin-1 com `;`.
  - Lê `data/inep_catalogo_escolas.csv` (UTF-8 com BOM, `,`).
  - Para se houver código vazio ou repetido em qualquer lado, ou coluna com
    o mesmo nome nas duas bases.
  - Junção externa por `CO_ENTIDADE` = `Código INEP`; separa as três saídas
    e imprime, para as sobras, a situação de cada escola.
  - Tudo lido e gravado como texto; saída em UTF-8 com `;`.
  - Opções: `--ano` (padrão 2025), `--cadastro`, `--saida`.
- Nomes das sobras padronizados com dois sublinhados (`__nocadastro_...`,
  `__nocenso_...`).

### Tarefa 4: `.gitignore`

- Nova entrada `data/inep_censo_escolar_*_+_cadastro_escolar_do_inep*.csv`.

### Tarefa 5: execução (28 s)

```sh
.venv/bin/python scripts/commands/inep_censo_escolar__juntar_cadastro_escolar.py
```

| Saída | Linhas | Tamanho |
|-------|-------:|--------:|
| Nas duas bases | 210.320 | 235,3 MB (310 colunas) |
| Só no Cadastro | 0 | - |
| Só no Censo 2025 | 3.872 | 1,7 MB |

- *Todas* as escolas do Cadastro estão no Censo 2025.
- As 3.872 só no Censo são todas extintas (`TP_SITUACAO_FUNCIONAMENTO = 3`):
  o Catálogo não lista escolas extintas.
- Nas duas bases, a situação bate: `TP_SITUACAO_FUNCIONAMENTO = 1` ↔ as
  quatro "Restrição de Atendimento" de escola em funcionamento (180.540);
  `= 2` ↔ "ESCOLA PARALISADA" (29.780).
- Com ponto do INEP: 155.771 (74%). Com endereço: 210.320 (100%).
- UF igual nas duas bases em todas as escolas menos uma: a 43145833 (RS,
  Sapiranga) vem com `SG_UF` e `NO_MUNICIPIO` vazios no próprio Censo 2025.

### Atualização (19/11/2026): junção externa

O CSV principal passou a ter *todas* as escolas (214.192), com a coluna
`JUNCAO_CENSO_CADASTRO` (`censo_e_cadastro`, `so_censo`, `so_cadastro`).
Os dois arquivos de sobras continuam. Ver
[campos-rastreio-etl-2025.md](campos-rastreio-etl-2025.md).
