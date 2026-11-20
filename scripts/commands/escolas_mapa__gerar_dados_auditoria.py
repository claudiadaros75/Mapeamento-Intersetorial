#!/usr/bin/env python3
"""Gera os arquivos por UF dos mapas de auditoria do georreferenciamento (web/escolas_auditoria*.html).

Um conjunto por ano do Censo Escolar (--ano):

    2024  entrada data/auditoria/escolas_inep_x_cnefe_2024.csv
          saida   web/data/auditoria/        (web/escolas_auditoria.html)
    2025  entrada data/inep_+cnef.csv (Censo 2025 + Catalogo + CNEFE, Brasil;
                  so as colunas usadas; o endereco do INEP e o "Endereço" do Catalogo)
          saida   web/data/auditoria_2025/   (web/escolas_auditoria_2025.html)

O mapa de auditoria mostra *de onde veio* a coordenada de cada escola,
separado do mapa do usuario final (web/escolas_mapa.html). Le:

    data/auditoria/escolas_inep_x_cnefe_2024.csv    (resultado do ETL, ver
                                                     escolas_dados__cruzar_inep_cnefe.py:
                                                     coordenada final, ponto do INEP e
                                                     ponto do CNEFE lado a lado)
    data/ibge_malha_municipal/zipfiles/BR_Municipios_2024.zip
                                                    (malha municipal em resolucao
                                                     maxima, para o teste "fora do municipio")

e grava web/data/auditoria/auditoria_<UF>_2024.json e indice.json.

A origem de cada ponto e o STATUS_GEOLOCALIZACAO final do ETL:

    endereco_exato, cep_numero
                   ponto do CNEFE, casamento por endereco (niveis 1 e 2)
    inep_confirmado, inep_proximo, inep_divergente, inep_sem_cnefe
                   ponto do Catalogo de Escolas do INEP, conforme a
                   distancia ate o ponto do CNEFE
    nome_exato, nome_ajustado
                   ponto do CNEFE, casamento por nome (niveis 3 e 4), para
                   escola sem coordenada no INEP ou com ponto do INEP repetido
    (sem ponto)    sem_correspondencia - entra so na contagem do indice

Para cada ponto, calcula a distancia (km) ate o municipio declarado no
Censo Escolar (0 = dentro) e em qual municipio ele cai. Quando a escola tem
as duas fontes, guarda tambem o ponto da outra fonte (OUTRO_*), para o mapa
ligar os dois.

Uso:
    .venv/bin/python scripts/commands/escolas_mapa__gerar_dados_auditoria.py              # 2024
    .venv/bin/python scripts/commands/escolas_mapa__gerar_dados_auditoria.py --ano 2025
"""

import argparse
import collections
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent.parent
ENTRADA_MUNICIPIOS = RAIZ / "data" / "ibge_malha_municipal" / "zipfiles" / "BR_Municipios_2024.zip"
DIR_WEB = RAIZ / "web"
# ano do Censo Escolar -> (CSV de entrada, pasta de saida)
POR_ANO = {
    "2024": (RAIZ / "data" / "auditoria" / "escolas_inep_x_cnefe_2024.csv", DIR_WEB / "data" / "auditoria"),
    "2025": (RAIZ / "data" / "inep_+cnef.csv", DIR_WEB / "data" / "auditoria_2025"),
}
# De onde vem o ponto do INEP (registrado no indice)
FONTE_PONTO_INEP = "Catalogo de Escolas do INEP (exportacao do painel do INEP Data)"

# Colunas lidas da entrada (o CSV de 2025 tem 372)
COLUNAS_ENTRADA = [
    "SG_UF", "CO_MUNICIPIO", "NO_MUNICIPIO", "CO_ENTIDADE", "NO_ENTIDADE",
    "LATITUDE", "LONGITUDE", "FONTE_COORDENADA", "STATUS_GEOLOCALIZACAO", "STATUS_CNEFE",
    "MOTIVO_GEOLOCALIZACAO", "ALERTAS_GEOLOCALIZACAO", "DIST_INEP_CNEFE_KM",
    "INEP_LATITUDE", "INEP_LONGITUDE", "CNEFE_LATITUDE", "CNEFE_LONGITUDE",
    "CNEFE_DSC_ESTABELECIMENTO", "CNEFE_ENDERECO", "CNEFE_NV_GEO_COORD", "SIMILARIDADE_NOME",
]

# Projecao em metros para distancias (SIRGAS 2000 / Brazil Polyconic)
CRS_METROS = "EPSG:5880"

# Colunas levadas para a web (a ordem define o indice de cada campo no JSON)
CAMPOS = [
    "CO_ENTIDADE",
    "NO_ENTIDADE",
    "CO_MUNICIPIO",
    "NO_MUNICIPIO",
    "ORIGEM",
    "LATITUDE",
    "LONGITUDE",
    "FORA_MUNICIPIO_KM",
    "MUNICIPIO_DO_PONTO",
    "OUTRO_FONTE",
    "OUTRO_LATITUDE",
    "OUTRO_LONGITUDE",
    "DIST_INEP_CNEFE_KM",
    "STATUS_CNEFE",
    "MOTIVO",
    "ALERTAS",
    "INEP_ENDERECO",
    "CNEFE_DSC_ESTABELECIMENTO",
    "CNEFE_ENDERECO",
    "CNEFE_NV_GEO_COORD",
    "SIMILARIDADE_NOME",
]


def pontos(df: pd.DataFrame, lat: str, lon: str) -> gpd.GeoSeries:
    """GeoSeries (EPSG:4674) com os pontos de df."""
    return gpd.GeoSeries(gpd.points_from_xy(df[lon], df[lat]), index=df.index, crs="EPSG:4674")


def distancia_ao_municipio(geometrias: gpd.GeoSeries, codigos: pd.Series, municipios: gpd.GeoDataFrame) -> pd.Series:
    """Distancia (km) de cada ponto ao poligono do seu municipio declarado; 0 = dentro."""
    poligonos = municipios.set_index("CD_MUN").geometry.to_crs(CRS_METROS)
    alvo = gpd.GeoSeries(poligonos.reindex(codigos.values).values, index=geometrias.index, crs=CRS_METROS)
    return (geometrias.to_crs(CRS_METROS).distance(alvo) / 1000).round(2)


def municipio_do_ponto(geometrias: gpd.GeoSeries, municipios: gpd.GeoDataFrame) -> pd.Series:
    """Nome do municipio onde o ponto realmente cai ("" se fora de todos, ex.: no mar)."""
    caidos = gpd.sjoin(
        gpd.GeoDataFrame(geometry=geometrias), municipios[["NM_MUN", "SIGLA_UF", "geometry"]], predicate="within"
    )
    caidos = caidos[~caidos.index.duplicated()]
    nomes = caidos["NM_MUN"] + "/" + caidos["SIGLA_UF"]
    return nomes.reindex(geometrias.index).fillna("")


def valor_web(valor):
    """Converte NaN em None e tipos do numpy em tipos do Python, para o JSON ficar enxuto."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    if isinstance(valor, float):
        return round(valor, 6)
    if hasattr(valor, "item"):  # inteiros do numpy/pandas
        return valor.item()
    return valor


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument("--ano", choices=sorted(POR_ANO), default="2024", help="ano do Censo Escolar (padrao: 2024)")
    ano = analisador.parse_args().ano
    entrada, dir_saida = POR_ANO[ano]
    print("Censo Escolar {}: {} -> {}".format(ano, entrada, dir_saida))

    # O endereco do INEP: coluna propria na auditoria de 2024; o "Endereço" do Catalogo em 2025
    cabecalho = pd.read_csv(entrada, sep=";", nrows=0).columns
    coluna_endereco = "INEP_ENDERECO" if "INEP_ENDERECO" in cabecalho else "Endereço"
    escolas = pd.read_csv(entrada, sep=";", dtype=str, keep_default_na=False,
                          usecols=COLUNAS_ENTRADA + [coluna_endereco])
    escolas = escolas.rename(columns={coluna_endereco: "INEP_ENDERECO"})
    numericas = ["LATITUDE", "LONGITUDE", "INEP_LATITUDE", "INEP_LONGITUDE", "CNEFE_LATITUDE", "CNEFE_LONGITUDE",
                 "DIST_INEP_CNEFE_KM"]
    for coluna in numericas:
        escolas[coluna] = pd.to_numeric(escolas[coluna], errors="coerce")
    escolas["ORIGEM"] = escolas["STATUS_GEOLOCALIZACAO"]

    plotadas = escolas[escolas["LATITUDE"].notna()].copy()

    # Ponto da outra fonte, quando a escola tem as duas
    da_inep = plotadas["FONTE_COORDENADA"] == "inep"
    plotadas["OUTRO_FONTE"] = None
    plotadas["OUTRO_LATITUDE"] = plotadas["CNEFE_LATITUDE"].where(da_inep, plotadas["INEP_LATITUDE"])
    plotadas["OUTRO_LONGITUDE"] = plotadas["CNEFE_LONGITUDE"].where(da_inep, plotadas["INEP_LONGITUDE"])
    tem_outro = plotadas["OUTRO_LATITUDE"].notna()
    plotadas.loc[tem_outro & da_inep, "OUTRO_FONTE"] = "cnefe"
    plotadas.loc[tem_outro & ~da_inep, "OUTRO_FONTE"] = "inep"

    geometrias = pontos(plotadas, "LATITUDE", "LONGITUDE")
    print("Lendo malha municipal (resolucao maxima)...")
    municipios = gpd.read_file("zip://{}".format(ENTRADA_MUNICIPIOS))
    municipios = municipios[municipios["SIGLA_UF"].isin(plotadas["SG_UF"].unique())]
    plotadas["FORA_MUNICIPIO_KM"] = distancia_ao_municipio(geometrias, plotadas["CO_MUNICIPIO"], municipios)
    plotadas["MUNICIPIO_DO_PONTO"] = municipio_do_ponto(geometrias, municipios)

    plotadas = plotadas.rename(columns={"MOTIVO_GEOLOCALIZACAO": "MOTIVO", "ALERTAS_GEOLOCALIZACAO": "ALERTAS"})
    plotadas["CNEFE_NV_GEO_COORD"] = pd.to_numeric(plotadas["CNEFE_NV_GEO_COORD"], errors="coerce").astype("Int64")
    plotadas["DIST_INEP_CNEFE_KM"] = plotadas["DIST_INEP_CNEFE_KM"].round(2)

    dir_saida.mkdir(parents=True, exist_ok=True)
    indice = {"ano_censo_escolar": ano, "fonte_ponto_inep": FONTE_PONTO_INEP, "ufs": {}}

    for uf in sorted(escolas["SG_UF"].unique()):
        da_uf = plotadas[plotadas["SG_UF"] == uf]
        linhas = [[valor_web(v) for v in linha] for linha in da_uf[CAMPOS].astype(object).itertuples(index=False)]
        nome_arquivo = "auditoria_{}_{}.json".format(uf, ano)
        caminho = dir_saida / nome_arquivo
        conteudo = {"uf": uf, "ano_censo_escolar": ano, "campos": CAMPOS, "escolas": linhas}
        caminho.write_text(json.dumps(conteudo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

        todas = escolas[escolas["SG_UF"] == uf]
        por_origem = collections.Counter(todas["ORIGEM"])
        fora = collections.Counter(da_uf.loc[da_uf["FORA_MUNICIPIO_KM"] > 0, "ORIGEM"])
        indice["ufs"][uf] = {
            "arquivo": caminho.relative_to(DIR_WEB).as_posix(),
            "tamanho_bytes": caminho.stat().st_size,
            "total_escolas": len(todas),
            "por_origem": dict(por_origem),
            "fora_do_municipio": dict(fora),
        }
        print(
            "{}: {} escolas, {} com ponto, por origem {}, fora do municipio {} -> {} ({:.1f} MB)".format(
                uf, len(todas), len(da_uf), dict(por_origem), dict(fora), caminho, caminho.stat().st_size / 1e6
            )
        )

    caminho_indice = dir_saida / "indice.json"
    caminho_indice.write_text(json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Indice: {}".format(caminho_indice))


if __name__ == "__main__":
    main()
