# Feature: Casamento com o CNEFE para o Brasil inteiro (Censo 2025)

- **Status**: Concluído
- **Data**: 2026-11-19
- **Componentes**: `scripts/commands/escolas_dados__cruzar_inep_cnefe.py`,
  `scripts/commands/escolas_dados__cruzar_censo_2025_cnefe.py`, `.gitignore`, `README.org`

## Objetivo

Baixar o CNEFE das 24 UFs que faltavam (já havia AM, PA e SP) e rodar o
casamento do Censo 2025 + Cadastro com o CNEFE para as 27 UFs, gerando
`data/inep_+cnef.csv` nacional.

## Restrições encontradas

- Disco com 5,5 GB livres. Os 24 ZIPs somam 2,7 GB (medido no servidor do
  IBGE); extraídos, ficariam em torno de 10 a 15 GB (SP: 1,1 GB → 3,6 GB).
  Não cabem extraídos.
- `data/inep_+cnef.csv` tinha 85 MB com 3 UFs (~24% das escolas); nacional,
  passa do limite de 100 MB por arquivo do GitHub.

## Tarefas

| # | Tarefa | Justificativa | Status |
|---|--------|---------------|--------|
| 1 | Baixar os 24 ZIPs do CNEFE sem extrair | Cabem no disco; extraídos não cabem. | Feito |
| 2 | ETL lê o CSV do CNEFE de dentro do ZIP quando não há pasta extraída | Dispensa a extração (10-15 GB) sem mudar o resultado; a pasta extraída continua valendo onde existe. | Feito |
| 3 | Script de 2025 processa e grava UF por UF | Com 214 mil escolas e 370 colunas, guardar todos os registros prontos na memória antes de gravar fica perto do limite da máquina. | Feito |
| 4 | Rodar as 27 UFs e conferir | Resultado nacional pedido; conferir que as 3 UFs já processadas não mudaram. | Feito |
| 5 | Tirar `data/inep_+cnef.csv` do git e pôr no `.gitignore` | O arquivo nacional passa de 100 MB e o push seria recusado. | Feito |
| 6 | Atualizar o README | O passo a passo dizia para baixar só AM, PA e SP e extrair. | Feito |

## O que foi feito

### Tarefa 1: download

```sh
.venv/bin/python scripts/commands/ibge_cnefe__baixar_dados.py ro ac rr ap to ma pi ce rn pb pe al se ba mg es rj pr sc rs ms mt go df
```

24 ZIPs baixados (2,7 GB), sem erro; os 27 abrem e têm um CSV cada. Disco
livre: 5,5 GB → 2,8 GB.

### Tarefa 2: ETL lê do ZIP

- `escolas_dados__cruzar_inep_cnefe.py`: nova `abrir_cnefe()` (pasta
  extraída se existir; senão `zipfile` + `io.TextIOWrapper`, latin-1);
  `ufs_com_cnefe_baixado()` aceita só o ZIP; mensagens sem `--extrair`.
- Conferido em AM: mesmos 7.052 pontos de ensino lidos da pasta (5,5 s) e
  do ZIP (6,0 s), registro a registro.

### Tarefa 3: script de 2025 por UF

- `principal()` grava cada UF num `.tmp` logo depois de processá-la e
  libera a memória da UF; no fim copia as linhas de UFs não reprocessadas
  e troca o arquivo.
- Escola com a UF incompleta no Censo (43145833, Sapiranga/RS: tem `CO_UF`
  e não tem `SG_UF`) passa a receber `SG_UF` do Cadastro. Na primeira
  rodada nacional ela saiu com `SG_UF` vazio; a linha foi corrigida no
  arquivo e o código conferido.
- Conferido: AM processado do ZIP com o script novo deu saída idêntica à
  do commit anterior (51.537 linhas, 372 colunas).

### Tarefa 4: Brasil

```sh
.venv/bin/python scripts/commands/escolas_dados__cruzar_censo_2025_cnefe.py   # 27 UFs: 10 min 12 s, 2,3 GB de memória
```

`data/inep_+cnef.csv`: 214.192 escolas (todas as da base juntada), 27 UFs,
372 colunas, 341 MB, códigos únicos.

| Status | Escolas | % |
|--------|--------:|--:|
| `endereco_exato` | 37.071 | 17,3 |
| `cep_numero` | 4.603 | 2,1 |
| `inep_confirmado` | 34.693 | 16,2 |
| `inep_proximo` | 1.111 | 0,5 |
| `inep_divergente` | 2.266 | 1,1 |
| `inep_sem_cnefe` | 83.908 | 39,2 |
| `nome_exato` | 3.076 | 1,4 |
| `nome_ajustado` | 4.930 | 2,3 |
| `sem_correspondencia` | 42.534 | 19,9 |

- Com coordenada: 171.658 (80,1%); em atividade: 158.860 de 180.540 (88,0%).
- `CNEFE_JUNTADO = sim` em 87.750, exatamente as que casaram.
- AM, PA e SP idênticos à rodada só com as 3 UFs.
- Cobertura por UF: de 54,5% (AC) e 63,8% (MT) a 92,5% (MS) e 95,4% (PR).

### Tarefas 5 e 6

- `git rm --cached data/inep_+cnef.csv` e entrada no `.gitignore` (a versão
  de 85 MB, só AM/PA/SP, segue no histórico, commit `d190cd5`).
- README: passo 1 baixa as 27 UFs sem extrair.
