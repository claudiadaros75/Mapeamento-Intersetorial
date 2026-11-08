#!/usr/bin/env python3
"""Gera os arquivos leves por UF que o mapa web de escolas (web/escolas_mapa.html) carrega.

Le o CSV do ETL (data/escolas_do_censo_2024_georeferenciadas_com_cnefe_2022.csv,
~400 colunas) e grava, para cada UF encontrada:

    web/data/escolas/escolas_<UF>_2024.json

so com as escolas que tem coordenada (status alta/media/baixa) e so com as
colunas usadas no mapa. O formato e colunar compacto - uma lista de campos e
uma lista de linhas - para o arquivo ficar pequeno:

    {"uf": "SP", "campos": ["CO_ENTIDADE", ...], "escolas": [[...], ...]}

Grava tambem web/data/escolas/indice.json com as UFs disponiveis e, por UF,
quantas escolas ficaram de fora do mapa (ambiguo/sem_correspondencia), para
que a pagina mostre esse numero em vez de esconder as escolas sem coordenada.

Uso:
    .venv/bin/python scripts/commands/escolas_mapa__gerar_dados_web.py
    .venv/bin/python ... --entrada outro.csv
"""

import argparse
import collections
import csv
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
ENTRADA_PADRAO = RAIZ / "data" / "escolas_do_censo_2024_georeferenciadas_com_cnefe_2022.csv"
DIR_SAIDA = RAIZ / "web" / "data" / "escolas"
ANO_CENSO_ESCOLAR = "2024"

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
    "CNEFE_NV_GEO_COORD",
    "CNEFE_DSC_ESTABELECIMENTO",
    "LATITUDE",
    "LONGITUDE",
]
CAMPOS_INTEIROS = {"TP_DEPENDENCIA", "TP_LOCALIZACAO", "TP_SITUACAO_FUNCIONAMENTO", "QT_MAT_BAS", "CNEFE_NV_GEO_COORD"}
STATUS_COM_COORDENADA = {"alta", "media", "baixa"}


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
    if campo in CAMPOS_INTEIROS:
        return int(valor) if valor else None
    return valor


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument(
        "--entrada",
        type=Path,
        default=ENTRADA_PADRAO,
        help="CSV gerado pelo ETL (padrao: {})".format(ENTRADA_PADRAO),
    )
    argumentos = analisador.parse_args()

    escolas_por_uf = collections.defaultdict(list)
    status_por_uf = collections.defaultdict(collections.Counter)

    with open(argumentos.entrada, encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo, delimiter=";"):
            uf = linha["SG_UF"]
            status = linha["STATUS_GEOLOCALIZACAO"]
            status_por_uf[uf][status] += 1
            if status in STATUS_COM_COORDENADA and linha["LATITUDE"] and linha["LONGITUDE"]:
                escolas_por_uf[uf].append([valor_web(campo, linha) for campo in CAMPOS])

    DIR_SAIDA.mkdir(parents=True, exist_ok=True)
    indice = {"ano_censo_escolar": ANO_CENSO_ESCOLAR, "ufs": {}}

    for uf in sorted(status_por_uf):
        nome_arquivo = "escolas_{}_{}.json".format(uf, ANO_CENSO_ESCOLAR)
        caminho = DIR_SAIDA / nome_arquivo
        conteudo = {"uf": uf, "ano_censo_escolar": ANO_CENSO_ESCOLAR, "campos": CAMPOS, "escolas": escolas_por_uf[uf]}
        caminho.write_text(json.dumps(conteudo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

        contagens = status_por_uf[uf]
        indice["ufs"][uf] = {
            "arquivo": "data/escolas/" + nome_arquivo,
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

    caminho_indice = DIR_SAIDA / "indice.json"
    caminho_indice.write_text(json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Indice: {}".format(caminho_indice))


if __name__ == "__main__":
    main()
