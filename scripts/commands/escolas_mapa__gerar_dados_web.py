#!/usr/bin/env python3
"""Gera os arquivos leves por UF que os mapas web de escolas (web/escolas_mapa.html, web/escolas_mapa_2025.html) carregam.

Um conjunto por ano do Censo Escolar (--ano):

    2024  entrada data/escolas_do_censo_2024_georeferenciadas_com_cnefe_2022.csv
          saida   web/data/escolas/            (web/escolas_mapa.html)
    2025  entrada data/inep_+cnef.csv (Censo 2025 + Catalogo + CNEFE, Brasil)
          saida   web/data/escolas_2025/       (web/escolas_mapa_2025.html)

Em 2025 a tabela de escolas do Censo nao tem mais as matriculas
(QT_MAT_BAS): elas vem da Tabela_Matricula_<ano>, dentro do ZIP do Censo,
ligadas pelo CO_ENTIDADE. Escolas sem linha nela (paralisadas, extintas)
ficam sem matriculas. O endereco de 2025 e o do Catalogo, separado pelo
ETL nas mesmas colunas do Censo.

Le o CSV do ETL (data/escolas_do_censo_2024_georeferenciadas_com_cnefe_2022.csv,
~400 colunas) e grava, para cada UF encontrada:

    web/data/escolas/escolas_<UF>_2024.json

so com as escolas que tem coordenada (do INEP ou do CNEFE, ver
STATUS_COM_COORDENADA) e so com as colunas usadas no mapa. O formato e colunar compacto - uma lista de campos e
uma lista de linhas - para o arquivo ficar pequeno:

    {"uf": "SP", "campos": ["CO_ENTIDADE", ...], "escolas": [[...], ...]}

Grava tambem web/data/escolas/indice.json com as UFs disponiveis e, por UF,
quantas escolas ficaram de fora do mapa (sem_correspondencia: sem ponto no
INEP nem no CNEFE), para
que a pagina mostre esse numero em vez de esconder as escolas sem coordenada.

Uso:
    .venv/bin/python scripts/commands/escolas_mapa__gerar_dados_web.py              # 2024
    .venv/bin/python scripts/commands/escolas_mapa__gerar_dados_web.py --ano 2025
    .venv/bin/python ... --entrada outro.csv
"""

import argparse
import collections
import csv
import io
import json
import re
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
DIR_WEB = RAIZ / "web"
DIR_ZIPS_CENSO = RAIZ / "data" / "inep_censo_escolar" / "zipfiles"
# ano do Censo Escolar -> (CSV de entrada, pasta de saida)
POR_ANO = {
    "2024": (RAIZ / "data" / "escolas_do_censo_2024_georeferenciadas_com_cnefe_2022.csv", DIR_WEB / "data" / "escolas"),
    "2025": (RAIZ / "data" / "inep_+cnef.csv", DIR_WEB / "data" / "escolas_2025"),
}

# Colunas levadas para a web (a ordem define o indice de cada campo no JSON)
CAMPOS = [
    "CO_ENTIDADE",
    "NO_ENTIDADE",
    "NO_MUNICIPIO",
    "TP_DEPENDENCIA",
    "TP_LOCALIZACAO",
    "TP_SITUACAO_FUNCIONAMENTO",
    "ENDERECO_CENSO",
    "QT_MAT_BAS",
    "STATUS_GEOLOCALIZACAO",
    "FONTE_COORDENADA",
    "DIST_INEP_CNEFE_KM",
    "ALERTAS_GEOLOCALIZACAO",
    "CNEFE_NV_GEO_COORD",
    "CNEFE_DSC_ESTABELECIMENTO",
    "LATITUDE",
    "LONGITUDE",
]
CAMPOS_INTEIROS = {"TP_DEPENDENCIA", "TP_LOCALIZACAO", "TP_SITUACAO_FUNCIONAMENTO", "QT_MAT_BAS", "CNEFE_NV_GEO_COORD"}
STATUS_COM_COORDENADA = {
    "inep_confirmado", "inep_proximo", "inep_divergente", "inep_sem_cnefe",
    "endereco_exato", "cep_numero", "nome_exato", "nome_ajustado",
}


def montar_endereco(linha: dict) -> str:
    """Endereco declarado no Censo Escolar, numa linha so."""
    partes = [linha["DS_ENDERECO"].strip()]
    if linha["NU_ENDERECO"].strip():
        partes[0] += ", " + linha["NU_ENDERECO"].strip()
    for coluna in ("DS_COMPLEMENTO", "NO_BAIRRO"):
        if linha[coluna].strip():
            partes.append(linha[coluna].strip())
    if linha["CO_CEP"].strip():
        partes.append("CEP " + linha["CO_CEP"].strip())
    return " - ".join(p for p in partes if p)


def valor_web(campo: str, linha: dict):
    if campo == "ENDERECO_CENSO":
        return montar_endereco(linha)
    valor = linha[campo].strip()
    if campo in ("LATITUDE", "LONGITUDE"):
        return round(float(valor), 6)
    if campo == "DIST_INEP_CNEFE_KM":
        return round(float(valor), 3) if valor else None
    if campo in CAMPOS_INTEIROS:
        return int(valor) if valor else None
    return valor


def carregar_matriculas(ano: str) -> dict:
    """CO_ENTIDADE -> QT_MAT_BAS, da Tabela_Matricula do ano, lida de dentro do ZIP do Censo."""
    caminho = DIR_ZIPS_CENSO / "microdados_censo_escolar_{}.zip".format(ano)
    padrao = re.compile(r"/dados/tabela_matricula_{}(_v\d+)?\.csv$".format(ano), re.I)
    with zipfile.ZipFile(caminho) as pacote:
        nomes = [nome for nome in pacote.namelist() if padrao.search(nome)]
        if len(nomes) != 1:
            raise SystemExit("esperava uma Tabela_Matricula em {}, achei {}".format(caminho.name, nomes))
        with pacote.open(nomes[0]) as binario:
            leitor = csv.DictReader(io.TextIOWrapper(binario, encoding="latin-1", newline=""), delimiter=";")
            matriculas = {linha["CO_ENTIDADE"]: linha["QT_MAT_BAS"] for linha in leitor}
    print("Matriculas: {} escolas em {}".format(len(matriculas), nomes[0]))
    return matriculas


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument("--ano", choices=sorted(POR_ANO), default="2024", help="ano do Censo Escolar (padrao: 2024)")
    analisador.add_argument("--entrada", type=Path, help="CSV gerado pelo ETL (padrao: o do ano, ver acima)")
    argumentos = analisador.parse_args()
    ano = argumentos.ano
    entrada, dir_saida = POR_ANO[ano]
    entrada = argumentos.entrada or entrada
    print("Censo Escolar {}: {} -> {}".format(ano, entrada, dir_saida))

    escolas_por_uf = collections.defaultdict(list)
    status_por_uf = collections.defaultdict(collections.Counter)

    with open(entrada, encoding="utf-8", newline="") as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=";")
        matriculas = None if "QT_MAT_BAS" in (leitor.fieldnames or []) else carregar_matriculas(ano)
        for linha in leitor:
            if matriculas is not None:
                linha["QT_MAT_BAS"] = matriculas.get(linha["CO_ENTIDADE"], "")
            uf = linha["SG_UF"]
            status = linha["STATUS_GEOLOCALIZACAO"]
            status_por_uf[uf][status] += 1
            if status in STATUS_COM_COORDENADA and linha["LATITUDE"] and linha["LONGITUDE"]:
                escolas_por_uf[uf].append([valor_web(campo, linha) for campo in CAMPOS])

    dir_saida.mkdir(parents=True, exist_ok=True)
    indice = {"ano_censo_escolar": ano, "ufs": {}}

    for uf in sorted(status_por_uf):
        nome_arquivo = "escolas_{}_{}.json".format(uf, ano)
        caminho = dir_saida / nome_arquivo
        conteudo = {"uf": uf, "ano_censo_escolar": ano, "campos": CAMPOS, "escolas": escolas_por_uf[uf]}
        caminho.write_text(json.dumps(conteudo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

        contagens = status_por_uf[uf]
        indice["ufs"][uf] = {
            "arquivo": caminho.relative_to(DIR_WEB).as_posix(),
            "tamanho_bytes": caminho.stat().st_size,
            "total_escolas": sum(contagens.values()),
            "no_mapa": len(escolas_por_uf[uf]),
            "por_status": dict(contagens),
        }
        print(
            "{}: {} de {} escolas no mapa -> {} ({:.1f} MB)".format(
                uf, len(escolas_por_uf[uf]), sum(contagens.values()), caminho, caminho.stat().st_size / 1e6
            )
        )

    caminho_indice = dir_saida / "indice.json"
    caminho_indice.write_text(json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Indice: {}".format(caminho_indice))


if __name__ == "__main__":
    main()
