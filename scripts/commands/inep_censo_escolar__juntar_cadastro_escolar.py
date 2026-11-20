#!/usr/bin/env python3
"""Junta a tabela de escolas do Censo Escolar ao Catalogo de Escolas do INEP pelo codigo da escola.

Le a tabela de escolas do Censo Escolar direto do ZIP baixado por
inep_censo_escolar__baixar_dados.py e o Catalogo de Escolas montado por
inep_cadastro_escolar__juntar_exportacoes.py, liga os dois pelo codigo
INEP (CO_ENTIDADE no Censo = "Código INEP" no Catalogo) e grava tres CSVs:

    data/inep_censo_escolar_<ano>_+_cadastro_escolar_do_inep.csv
        todas as escolas (juncao externa): JUNCAO_CENSO_CADASTRO
        (censo_e_cadastro, so_censo ou so_cadastro), as colunas do Censo e
        as do Catalogo - vazias do lado em que a escola nao esta
    ..._+_cadastro_escolar_do_inep__nocadastro_forado_censo.csv
        escolas so no Catalogo (colunas do Catalogo)
    ..._+_cadastro_escolar_do_inep__nocenso_forado_cadastroescolar.csv
        escolas so no Censo (colunas do Censo)

Os microdados de 2025 nao trazem endereco nem coordenada; o Catalogo traz
(Endereço, Latitude, Longitude). Todos os valores sao lidos e gravados
como texto, para nao perder zeros a esquerda nem virar 1.0. Saida em
UTF-8 com separador ";", como os outros CSVs do projeto.

Uso:
    .venv/bin/python scripts/commands/inep_censo_escolar__juntar_cadastro_escolar.py
    .venv/bin/python ... --ano 2025 --cadastro data/inep_catalogo_escolas.csv
"""

import argparse
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent.parent
PASTA_ZIPS = RAIZ / "data" / "inep_censo_escolar" / "zipfiles"
CADASTRO = RAIZ / "data" / "inep_catalogo_escolas.csv"
PASTA_SAIDA = RAIZ / "data"
ANO_PADRAO = "2025"

CODIGO_CENSO = "CO_ENTIDADE"
CODIGO_CADASTRO = "Código INEP"

# Primeira coluna da base juntada: em qual das duas bases a escola esta
COLUNA_JUNCAO = "JUNCAO_CENSO_CADASTRO"
VALORES_JUNCAO = {"both": "censo_e_cadastro", "left_only": "so_censo", "right_only": "so_cadastro"}


def sair(mensagem: str) -> None:
    print("ERRO: " + mensagem, file=sys.stderr)
    sys.exit(1)


def ler_censo(ano: str) -> pd.DataFrame:
    """Tabela de escolas do Censo do ano, lida de dentro do ZIP (latin-1, ';').

    A partir de 2025 a tabela se chama Tabela_Escola_<ano>[_V2].csv; ate 2024
    era microdados_ed_basica_<ano>.csv.
    """
    caminho = PASTA_ZIPS / "microdados_censo_escolar_{}.zip".format(ano)
    if not caminho.exists():
        sair("nao achei {} - baixe com: .venv/bin/python "
             "scripts/commands/inep_censo_escolar__baixar_dados.py {}".format(caminho, ano))
    padrao = re.compile(r"/dados/(tabela_escola_{0}(_v\d+)?|microdados_ed_basica_{0})\.csv$".format(ano), re.I)
    with zipfile.ZipFile(caminho) as arquivo_zip:
        nomes = [nome for nome in arquivo_zip.namelist() if padrao.search(nome)]
        if len(nomes) != 1:
            sair("esperava uma tabela de escolas em {}, achei {}".format(caminho.name, nomes))
        print("Censo Escolar {}: {} -> {}".format(ano, caminho.name, nomes[0]))
        with arquivo_zip.open(nomes[0]) as arquivo:
            return pd.read_csv(arquivo, sep=";", encoding="latin-1", dtype=str, keep_default_na=False)


def ler_cadastro(caminho: Path) -> pd.DataFrame:
    """Catalogo de Escolas exportado do painel do INEP Data (utf-8 com BOM, ',')."""
    if not caminho.exists():
        sair("nao achei {} - monte com: .venv/bin/python "
             "scripts/commands/inep_cadastro_escolar__juntar_exportacoes.py".format(caminho))
    print("Cadastro Escolar (Catalogo de Escolas do INEP Data): {}".format(caminho))
    return pd.read_csv(caminho, dtype=str, encoding="utf-8-sig", keep_default_na=False)


def conferir_codigos(tabela: pd.DataFrame, coluna: str, rotulo: str) -> None:
    """Para se houver codigo vazio ou repetido: a juncao duplicaria ou perderia linhas sem aviso."""
    tabela[coluna] = tabela[coluna].str.strip()
    vazios = int((tabela[coluna] == "").sum())
    repetidos = tabela.loc[tabela[coluna].duplicated(keep=False), coluna].unique()
    if vazios or len(repetidos):
        sair("{}: {} codigos vazios e {} repetidos (ex.: {})".format(
            rotulo, vazios, len(repetidos), list(repetidos[:5])))
    print("    {} escolas, codigos unicos".format(len(tabela)))


def contar(tabela: pd.DataFrame, coluna: str, titulo: str) -> None:
    """Imprime a contagem de uma coluna, para entender quem ficou de fora."""
    if coluna not in tabela.columns or tabela.empty:
        return
    print("    {}:".format(titulo))
    for valor, quantidade in tabela[coluna].value_counts().items():
        print("      {:>7}  {}".format(quantidade, valor or "(vazio)"))


def gravar(tabela: pd.DataFrame, caminho: Path) -> None:
    tabela.to_csv(caminho, sep=";", index=False, encoding="utf-8")
    print("    {} linhas -> {} ({:.1f} MB)".format(len(tabela), caminho, caminho.stat().st_size / 1e6))


def principal() -> None:
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument("--ano", default=ANO_PADRAO, help="ano do Censo Escolar (padrao: {})".format(ANO_PADRAO))
    analisador.add_argument("--cadastro", type=Path, default=CADASTRO,
                            help="Catalogo de Escolas (padrao: {})".format(CADASTRO))
    analisador.add_argument("--saida", type=Path, default=PASTA_SAIDA,
                            help="pasta dos CSVs (padrao: {})".format(PASTA_SAIDA))
    argumentos = analisador.parse_args()

    censo = ler_censo(argumentos.ano)
    conferir_codigos(censo, CODIGO_CENSO, "Censo")
    cadastro = ler_cadastro(argumentos.cadastro)
    conferir_codigos(cadastro, CODIGO_CADASTRO, "Cadastro")

    repetidas = set(censo.columns) & set(cadastro.columns)
    if repetidas:
        sair("colunas com o mesmo nome nas duas bases: {}".format(sorted(repetidas)))

    juntas = censo.merge(cadastro, how="outer", left_on=CODIGO_CENSO, right_on=CODIGO_CADASTRO, indicator=True)
    juntas.insert(0, COLUNA_JUNCAO, juntas["_merge"].map(VALORES_JUNCAO).astype(str))
    juntas = juntas.drop(columns="_merge")
    so_cadastro = juntas.loc[juntas[COLUNA_JUNCAO] == "so_cadastro", list(cadastro.columns)]
    so_censo = juntas.loc[juntas[COLUNA_JUNCAO] == "so_censo", list(censo.columns)]

    base = "inep_censo_escolar_{}_+_cadastro_escolar_do_inep".format(argumentos.ano)
    argumentos.saida.mkdir(parents=True, exist_ok=True)
    print("\nTodas as escolas: {}".format(len(juntas)))
    contar(juntas, COLUNA_JUNCAO, COLUNA_JUNCAO)
    gravar(juntas, argumentos.saida / "{}.csv".format(base))
    print("So no Cadastro: {}".format(len(so_cadastro)))
    contar(so_cadastro, "Restrição de Atendimento", "situacao no Cadastro")
    gravar(so_cadastro, argumentos.saida / "{}__nocadastro_forado_censo.csv".format(base))
    print("So no Censo {}: {}".format(argumentos.ano, len(so_censo)))
    contar(so_censo, "TP_SITUACAO_FUNCIONAMENTO", "TP_SITUACAO_FUNCIONAMENTO (1 em atividade, 2 paralisada, 3 extinta)")
    gravar(so_censo, argumentos.saida / "{}__nocenso_forado_cadastroescolar.csv".format(base))


if __name__ == "__main__":
    principal()
