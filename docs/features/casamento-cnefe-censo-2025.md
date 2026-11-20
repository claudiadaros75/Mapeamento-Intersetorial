# Feature: Casamento com o CNEFE para o Censo Escolar 2025

- **Status**: Concluído
- **Data**: 2026-11-19
- **Componentes**: `scripts/commands/escolas_dados__cruzar_censo_2025_cnefe.py`

## Objetivo

Rodar o mesmo algoritmo de casamento com o CNEFE 2022 (níveis 1 a 4) e a
mesma escolha de coordenada do ETL do Censo 2024 sobre
`data/inep_censo_escolar_2025_+_cadastro_escolar_do_inep.csv` (Censo 2025
juntado ao Catálogo de Escolas), gravando `data/inep_+cnef.csv`.

## O problema

Os microdados de 2025 não trazem endereço. O endereço vem do Catálogo, mas
num campo só (`Endereço`), no formato
`LOGRADOURO, NÚMERO [COMPLEMENTO]. [BAIRRO]. CEP Município - UF.`, com
partes opcionais. Os níveis 1 e 2 precisam de CEP, número e logradouro
separados.

## Tarefas

| # | Tarefa | Justificativa | Status |
|---|--------|---------------|--------|
| 1 | Separar o `Endereço` em logradouro, número, complemento, bairro e CEP | Os níveis 1 e 2 comparam CEP + número + rua; sem separar, só sobrariam os níveis por nome. | Feito |
| 2 | Medir o separador contra os campos do Censo 2024 | É a única base com os mesmos campos já separados; mostra se o separador erra. | Feito |
| 3 | Script que reaproveita o ETL (`processar_uf`, `escolher_coordenada`, `gravar_mesclando`) | Um algoritmo só para os dois anos: qualquer ajuste no ETL vale também para 2025. | Feito |
| 4 | Rodar para as UFs com CNEFE (AM, PA, SP) e comparar com o resultado de 2024 | Saber se o endereço do Catálogo casa tão bem quanto o dos microdados de 2024. | Feito |

## O que foi feito

### Tarefas 1 e 2: separador de endereço

- `separar_endereco()` em `scripts/commands/escolas_dados__cruzar_censo_2025_cnefe.py`:
  CEP pelo fim do texto (`99999-999 Município - UF.`); logradouro até a
  última vírgula seguida de número (o logradouro pode ter vírgula: `R. X,
  QD. 2, 23`); número = token com dígito, `S/N` e variantes, ou prefixo +
  dígitos (`KM 35`, `N 21`); depois, um trecho = bairro, dois = complemento
  e bairro.
- Medido contra os campos separados do Censo 2024 (AM, PA, SP; 50.137
  escolas nas duas bases), com as normalizações do ETL:

  | Campo | Igual ao Censo 2024 |
  |-------|--------------------:|
  | CEP | 92,4% |
  | Número | 97,2% |
  | Logradouro (conjunto de palavras) | 91,2% |
  | Bairro (texto exato) | 72,2% |

  As diferenças olhadas uma a uma são, na maioria, endereço que mudou no
  cadastro (outro CEP, outro número, rua renomeada), não erro do separador.
  Os ajustes de vírgula no logradouro e prefixo de número subiram o número
  de 96,9% para 97,2% e o logradouro de 91,0% para 91,2%.

### Tarefa 3: script

- `scripts/commands/escolas_dados__cruzar_censo_2025_cnefe.py` importa o ETL
  (`escolas_dados__cruzar_inep_cnefe.py`) e usa `processar_uf`,
  `ufs_com_cnefe_baixado` e `gravar_mesclando` sem cópia do algoritmo.
- Lê a base juntada; separa o `Endereço` nas colunas `DS_ENDERECO`,
  `NU_ENDERECO`, `DS_COMPLEMENTO`, `NO_BAIRRO`, `CO_CEP`; o ponto do INEP vem
  de `Latitude`/`Longitude` (contagem de escolas no mesmo ponto no Brasil todo).
- Saída `data/inep_+cnef.csv`: colunas da entrada + as 5 de endereço + as
  colunas de geolocalização do ETL. Mesclada por UF, como no ETL.
- Não grava os arquivos de auditoria nem as cópias marcadas (só o pedido).

### Tarefa 4: execução e comparação com 2024

```sh
.venv/bin/python scripts/commands/escolas_dados__cruzar_censo_2025_cnefe.py   # AM, PA, SP (1 min 46 s)
```

| Status | Escolas | % |
|--------|--------:|--:|
| `endereco_exato` | 13.197 | 25,9 |
| `cep_numero` | 1.253 | 2,5 |
| `inep_confirmado` | 7.562 | 14,8 |
| `inep_proximo` | 192 | 0,4 |
| `inep_divergente` | 478 | 0,9 |
| `inep_sem_cnefe` | 20.792 | 40,8 |
| `nome_exato` | 266 | 0,5 |
| `nome_ajustado` | 806 | 1,6 |
| `sem_correspondencia` | 6.433 | 12,6 |
| *Total* | 50.979 | |

- Com coordenada: 44.546 de 50.979 (87,4%); em 2024, 44.989 de 51.892 (86,7%).
- 50.137 escolas estão nos dois anos; 842 só em 2025.
- Nas escolas em comum, a coordenada final é a mesma em 48.712 (97,2%);
  92 perderam coordenada e 51 ganharam.
- 1.366 escolas casadas por endereço (níveis 1-2) em 2024 não casam por
  endereço em 2025: *todas* têm CEP (1.223) ou número (233) diferente no
  cadastro atual. 1.286 delas seguem com coordenada (ponto do INEP).
