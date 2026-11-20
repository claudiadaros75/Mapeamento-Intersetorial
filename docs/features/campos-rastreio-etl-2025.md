# Feature: Campos de rastreio do processamento (Censo 2025 + Cadastro + CNEFE)

- **Status**: Concluído
- **Data**: 2026-11-19
- **Componentes**: `scripts/commands/inep_censo_escolar__juntar_cadastro_escolar.py`,
  `scripts/commands/escolas_dados__cruzar_censo_2025_cnefe.py`

## Objetivo

Cada registro de `data/inep_+cnef.csv` deve dizer, em campos próprios, o que
aconteceu com ele em cada etapa (junção Censo × Cadastro, separação do
endereço, casamento com o CNEFE, escolha da coordenada), sem perder dado de
nenhuma coluna: quando a escola casa com um ponto do CNEFE, a linha
original do CNEFE inteira entra no registro.

## Decisões

- O CSV juntado passa a ter *todas* as escolas (junção externa), com a
  coluna `JUNCAO_CENSO_CADASTRO`. Os dois arquivos de sobras continuam.
- A linha do CNEFE entra sempre que há casamento (níveis 1 a 4), mesmo
  quando a coordenada final é a do INEP: o casamento aconteceu e os dados
  dele interessam. Se a coordenada veio do CNEFE ou do INEP está em
  `FONTE_COORDENADA`.
- Colunas originais do CNEFE com o prefixo `CNEFE_`. As que o ETL já
  gravava com o mesmo nome (`CNEFE_LATITUDE`, `CNEFE_LONGITUDE`,
  `CNEFE_COD_UNICO_ENDERECO`, `CNEFE_NV_GEO_COORD`,
  `CNEFE_DSC_ESTABELECIMENTO`) têm o mesmo valor e não se repetem.

## Tarefas

| # | Tarefa | Justificativa | Status |
|---|--------|---------------|--------|
| 1 | `JUNCAO_CENSO_CADASTRO` e junção externa no CSV juntado | Escolas só no Censo (ou só no Cadastro) não podem sumir do resultado; o campo diz por que não têm dados do Cadastro. | Feito |
| 2 | `ENDERECO_SEPARACAO` | Os níveis 1 e 2 exigem CEP e número; o campo explica por que uma escola nem chegou a tentar o casamento por endereço. | Feito |
| 3 | Campos da auditoria no registro (`N_CANDIDATOS`, `SIMILARIDADE_NOME`, nomes normalizados, endereço do CNEFE) | Hoje só existem no CSV de auditoria do ETL de 2024; são o "porquê" do casamento. | Feito |
| 4 | Linha do CNEFE inteira (`CNEFE_*`) e `CNEFE_JUNTADO` | Pedido explícito: nenhum dado do CNEFE se perde quando a escola casa com ele. | Feito |
| 5 | `HISTORICO_PROCESSAMENTO` | Um texto curto que conta as etapas em ordem, para ler o registro sem conhecer todas as colunas. | Feito |
| 6 | Rodar, conferir e registrar | Garantir que nenhuma escola sumiu e que os números do casamento não mudaram com a junção externa. | Feito |

## O que foi feito

### Tarefa 1: junção externa

- `inep_censo_escolar__juntar_cadastro_escolar.py`: a base juntada tem agora
  as 214.192 escolas, com `JUNCAO_CENSO_CADASTRO` na primeira coluna
  (`censo_e_cadastro` 210.320, `so_censo` 3.872, `so_cadastro` 0). Os dois
  arquivos de sobras continuam. Tamanho: 240,7 MB.

### Tarefas 2 a 5: campos no `inep_+cnef.csv`

`escolas_dados__cruzar_censo_2025_cnefe.py`:

- `ENDERECO_SEPARACAO` (`situacao_endereco`): `cep_e_numero`, `sem_numero`,
  `sem_cep`, `sem_cep_e_numero`, `sem_endereco`.
- `montar_registros`: junta a cada escola os campos da auditoria do ETL
  (`N_CANDIDATOS`, `SIMILARIDADE_NOME`, `INEP_NOME_NORMALIZADO`,
  `INEP_NUCLEO_NOME`, `CNEFE_NOME_NORMALIZADO`, `CNEFE_NUCLEO_NOME`,
  `CNEFE_ENDERECO`) e a linha original do CNEFE (34 colunas com prefixo
  `CNEFE_`, 29 novas), a partir do que `processar_uf` já devolve; o ETL
  não foi alterado.
- `CNEFE_JUNTADO` (`sim`/`nao`) e `HISTORICO_PROCESSAMENTO` (5 etapas fixas:
  junção, endereço, ponto do INEP, CNEFE com alertas, coordenada). Exemplo:

  `1 juncao: censo_e_cadastro | 2 endereco: cep_e_numero | 3 ponto_inep: sim (2 escola(s) no ponto) | 4 cnefe: nivel 2 cep_numero (1 candidato(s), similaridade do nome 0.438), alertas cep_generico | 5 coordenada: inep (inep_divergente), INEP x CNEFE 62.619 km`

- Escola só do Cadastro (nenhuma hoje) recebe `CO_ENTIDADE`, `SG_UF` e
  `CO_UF` do Cadastro, para não ficar de fora.

### Tarefa 6: execução e conferência

- `data/inep_+cnef.csv`: 51.537 escolas (AM, PA, SP), 372 colunas.
  `censo_e_cadastro` 50.979 + `so_censo` 558: nenhuma escola sumiu.
- `CNEFE_JUNTADO = sim` em 23.810, exatamente as que casaram (níveis 1-4);
  todas com `CNEFE_COD_ESPECIE = 4` e CEP preenchido. Nenhuma casada sem a
  linha do CNEFE e nenhuma linha do CNEFE sem casamento.
- `ENDERECO_SEPARACAO`: `cep_e_numero` 33.342, `sem_numero` 17.637,
  `sem_endereco` 558. Os `sem_numero` são S/N de verdade (SN 8.558, vazio
  5.362, S/N 3.313...); em 2024 eram 18.232 sem número.
- Efeito das 558 escolas extintas (só no Censo) no casamento das outras
  50.979: 8 escolas perderam o casamento `nome_ajustado`, porque uma escola
  extinta com o mesmo núcleo de nome no município tornou o nome repetido
  (`nome_repetido_inep`); 1 delas perdeu a coordenada. Nenhuma outra
  mudou. As extintas casaram 64 pontos por nome (10 `nome_exato`, 54
  `nome_ajustado`). É o mesmo comportamento do ETL de 2024, que também
  processa as extintas do Censo.
