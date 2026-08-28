#!/usr/bin/env python3
"""Primeira exploracao da Malha Municipal Digital 2024 do IBGE.

Le um shapefile com geopandas e imprime um retrato dele: numero de feicoes,
CRS, extensao, tabela de atributos e alguns recortes por regiao e por area.

O relatorio usa colunas especificas da malha *municipal* (CD_MUN, NM_MUN,
NM_REGIA, AREA_KM2, NM_CONCU), que existem no shapefile do IBGE mas nao no
GeoJSON da API. Apontar para outro recorte (UF, regioes) levanta KeyError.

Depende do ZIP ja extraido:
    .venv/bin/python scripts/ibge_malha_municipal__baixar_dados_formato_shapefile.py \
        municipios --extrair

Uso:
    .venv/bin/python scripts/ibge_malha_municipal__explorar_shapefiles.py [caminho_do_shapefile]

Caminho padrao: data/BR_Municipios_2024/BR_Municipios_2024.shp
"""

import sys

import geopandas as gpd

CAMINHO_PADRAO = "data/BR_Municipios_2024/BR_Municipios_2024.shp"


def principal():
    """Abre o shapefile indicado (ou o padrao) e imprime o relatorio."""
    caminho = sys.argv[1] if len(sys.argv) > 1 else CAMINHO_PADRAO
    malha = gpd.read_file(caminho)

    print("=== Malha Municipal Digital 2024 ===")
    print("arquivo:", caminho)
    print("feicoes (linhas):", malha.shape[0])
    print("colunas:", malha.shape[1])
    print("geocodigos unicos:", malha["CD_MUN"].nunique())
    print("tipos de geometria:", malha.geometry.geom_type.unique().tolist())
    print("CRS:", malha.crs)
    print("extensao (bounds):", malha.total_bounds)

    print("\n=== Atributos (colunas) ===")
    print(malha.dtypes)

    print("\n=== Distribuicao por regiao ===")
    print(malha.groupby("NM_REGIA").size())

    print("\n=== UFs com mais municipios ===")
    print(malha.groupby(["SIGLA_UF", "NM_UF"]).size().sort_values(ascending=False).head(5))

    print("\n=== Area ===")
    print("area total (km2):", round(malha["AREA_KM2"].sum(), 1))
    menor = malha.loc[malha["AREA_KM2"].idxmin()]
    maior = malha.loc[malha["AREA_KM2"].idxmax()]
    print("menor municipio:", menor["NM_MUN"], "/", menor["SIGLA_UF"], "/", menor["AREA_KM2"], "km2")
    print("maior municipio:", maior["NM_MUN"], "/", maior["SIGLA_UF"], "/", maior["AREA_KM2"], "km2")

    print("\n=== Concentracoes urbanas (NM_CONCU) ===")
    print("municipios com concu:", int(malha["NM_CONCU"].notna().sum()))
    print("exemplos:", sorted(malha["NM_CONCU"].dropna().unique())[:3])


if __name__ == "__main__":
    principal()