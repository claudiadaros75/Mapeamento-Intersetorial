# Explorar os microdados do Censo Escolar pela linha de comando

## Goal

Ter um script básico, `scripts/commands/explorardados.py`, para olhar os
microdados do Censo Escolar (começando por 2025) sem abrir um notebook: ver
as tabelas, as colunas, as primeiras e as últimas linhas, contar valores,
filtrar e consultar o dicionário de dados do INEP.

## Scope

- Entra: o ZIP baixado por `inep_censo_escolar__baixar_dados.py`
  (`data/inep_censo_escolar/zipfiles/microdados_censo_escolar_<ano>.zip`),
  lido direto, sem precisar extrair; ou qualquer CSV passado com `--arquivo`.
- Sai: só texto na tela. Opcionalmente, um CSV com o resultado de `filtrar`.
- Fora: gráficos, cruzamento entre tabelas, anos anteriores a 2025 com layout
  diferente (o script deve funcionar com eles, mas não foi testado com eles).

## Task Breakdown

| # | Tarefa | Justificativa | Estado |
|---|--------|---------------|--------|
| 1 | Ler os CSVs direto do ZIP, com nome curto da tabela (`escola`, `matricula`...) | O ZIP de 2025 tem 537 MB; extrair duplica o espaço em disco só para olhar os dados. Nome curto evita digitar `Tabela_Escola_2025_V2.csv`. | Feito |
| 2 | Subcomandos `tabelas`, `colunas`, `head`, `tail`, `amostra` | É o mínimo para conhecer uma tabela nova: o que existe, que colunas tem e como são as linhas. | Feito |
| 3 | Mostrar as linhas na vertical quando há muitas colunas | A tabela de escolas tem centenas de colunas; na horizontal o pandas corta a saída e nada fica legível. | Feito |
| 4 | Subcomandos `contar`, `resumo` e `filtrar` (em blocos) | Distribuições (ex.: escolas por UF) e recortes (ex.: só AM) são as primeiras perguntas da exploração. Ler em blocos mantém a memória baixa com CSVs de mais de 100 MB. | Feito |
| 5 | Subcomando `dicionario` e rótulos em `contar` | Colunas `TP_*` são códigos (1, 2, 3...); sem o dicionário não dá para interpretar. O `.xlsx` vem no próprio ZIP e é lido com a biblioteca padrão, sem acrescentar o openpyxl ao ambiente. | Feito |
| 6 | Testar cada subcomando com o ZIP de 2025 | Confirmar que funciona com os dados reais e medir o tempo dos comandos que leem a tabela inteira. | Feito |

## What Was Done

### Tarefas 1 a 5 (19/11/2026)

- Arquivo criado: `scripts/commands/explorardados.py` (só pandas e a
  biblioteca padrão; nada novo no `.venv`).
- Subcomandos: `tabelas`, `colunas`, `head`, `tail`, `amostra`, `contar`,
  `resumo`, `filtrar`, `dicionario`. Opções comuns: `--ano`, `--arquivo`,
  `--sep`, `--encoding`. Exemplos no início do script.
- Decisões:
  - Tudo é lido como texto, para que códigos (`CO_ENTIDADE`, `TP_*`) apareçam
    como no arquivo (`1`, e não `1.0`). Em `--onde`, as colunas comparadas com
    `> < >= <=` são convertidas para número automaticamente; `==` compara
    texto (`TP_DEPENDENCIA == '3'`).
  - Com mais de 8 colunas, `head`/`tail`/`amostra`/`filtrar` mostram a tabela
    na vertical; `--sem-vazias` esconde as colunas vazias.
  - `amostra` é uniforme entre todas as linhas (cada linha recebe um número
    aleatório e ficam as N menores), e `--semente` repete a mesma amostra.
  - O dicionário (`.xlsx` do ZIP) é lido com `zipfile` + `xml.etree`; as
    colunas são achadas pelo cabeçalho ("Nome da Variável", "Categoria"...).
    `contar` usa as categorias para pôr a coluna `significado`.
  - Apelido `escola` → `microdados_ed_basica` para anos até 2024, quando a
    tabela de escolas era um CSV único.
  - Com `--arquivo`, a codificação é detectada (utf-8 ou latin-1).

### Tarefa 6 (19/11/2026)

Testes com o ZIP de 2025 (e `--ano 2024` e `--arquivo` com um CSV do projeto):

```
$ explorardados.py contar escola TP_DEPENDENCIA
== escola (Tabela_Escola_2025_V2.csv): TP_DEPENDENCIA ==
               significado  linhas      %
3                Municipal  128145  59.83
4                  Privada   51758  24.16
2                 Estadual   33561  15.67
1                  Federal     728   0.34
(214.192 linha(s); 4 valor(es) distinto(s))
```

| Comando | Tempo |
|---------|------:|
| `contar`, `tail`, `amostra`, `filtrar` na tabela de escolas | ~4 s |
| `resumo matricula --colunas` (4 colunas) | ~4 s |
| `resumo escola` (290 colunas) | ~52 s |

Também conferidos: erro claro para tabela/coluna inexistente e para `--onde`
com `=` em vez de `==` (o pandas trataria como atribuição e devolveria a
tabela inteira).

Achado nos dados: a escola `43145833` (ESCOLA MUNICIPAL DE EDUCACAO BASICA 25
DE JULHO, `CO_UF` 43 = RS) vem com `NO_UF`, `SG_UF`, `NO_REGIAO` e
`NO_MUNICIPIO` vazios nas tabelas de escola e matrícula de 2025. É do
arquivo do INEP, não do script.
