#!/usr/bin/env python3
"""Gera os arquivos por UF do mapa de auditoria do georreferenciamento (web/escolas_auditoria.html).

O mapa de auditoria mostra *de onde veio* a coordenada de cada escola,
separado do mapa do usuario final (web/escolas_mapa.html). Le:

    data/auditoria/escolas_inep_x_cnefe_2024.csv    (resultado do casamento, ver
                                                     escolas_dados__cruzar_inep_cnefe.py)
    data/ipea_geobr_escolas/schools_2023.gpkg       (coordenadas do INEP, ver
                                                     ipea_geobr_escolas__baixar_dados.py)
    data/ibge_malha_municipal/zipfiles/BR_Municipios_2024.zip
                                                    (malha municipal em resolucao
                                                     maxima, para o teste "fora do municipio")

e grava web/data/auditoria/auditoria_<UF>_2024.json e indice.json.

Origem da coordenada de cada escola:

    cep_numero     nivel 1  - CNEFE, mesmo CEP + numero
    nome_exato     nivel 2a - CNEFE, mesmo nome exato + municipio
    nome_ajustado  nivel 2b - CNEFE, mesmo nucleo do nome + municipio
    inep           sem correspondencia no CNEFE, coordenada do Catalogo de
                   Escolas do INEP (geobr, cadastro de 2023)
    (sem ponto)    sem correspondencia e sem coordenada do INEP - entra so
                   na contagem do indice

Para cada ponto, calcula a distancia (km) ate o municipio declarado no
Censo Escolar (0 = dentro). Quando a escola tem ponto do CNEFE e do INEP,
guarda tambem o ponto do INEP e a distancia entre os dois.

Uso:
    .venv/bin/python scripts/commands/escolas_mapa__gerar_dados_auditoria.py
"""

import argparse
import collections
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent.parent
ENTRADA_AUDITORIA = RAIZ / "data" / "auditoria" / "escolas_inep_x_cnefe_2024.csv"
ENTRADA_INEP = RAIZ / "data" / "ipea_geobr_escolas" / "schools_2023.gpkg"
ENTRADA_MUNICIPIOS = RAIZ / "data" / "ibge_malha_municipal" / "zipfiles" / "BR_Municipios_2024.zip"
DIR_SAIDA = RAIZ / "web" / "data" / "auditoria"
ANO_CENSO_ESCOLAR = "2024"

# Projecao em metros para distancias (SIRGAS 2000 / Brazil Polyconic)
CRS_METROS = "EPSG:5880"

STATUS_CNEFE = {"cep_numero", "nome_exato", "nome_ajustado"}

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
    "INEP_LATITUDE",
    "INEP_LONGITUDE",
    "DIST_CNEFE_INEP_KM",
    "MOTIVO",
    "ALERTAS",
    "INEP_ENDERECO",
    "CNEFE_DSC_ESTABELECIMENTO",
    "CNEFE_ENDERECO",
    "CNEFE_NV_GEO_COORD",
    "SIMILARIDADE_NOME",
]


def pontos(df: pd.DataFrame, lat: str, lon: str) -> gpd.GeoSeries:
    """GeoSeries (EPSG:4674) com os pontos de df; linhas sem coordenada viram vazias."""
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
    """Converte NaN em None e floats inteiros em int, para o JSON ficar enxuto."""
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return None
    if isinstance(valor, float):
        return round(valor, 6)
    if hasattr(valor, "item"):  # inteiros do numpy/pandas
        return valor.item()
    return valor


def main() -> None:
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.parse_args()

    escolas = pd.read_csv(ENTRADA_AUDITORIA, sep=";", dtype=str, keep_default_na=False)
    for coluna in ("LATITUDE", "LONGITUDE"):
        escolas[coluna] = pd.to_numeric(escolas[coluna], errors="coerce")

    inep = gpd.read_file(ENTRADA_INEP, columns=["code_school"])
    inep = inep[~(inep.geometry.is_empty | inep.geometry.isna())]
    inep = pd.DataFrame(
        {
            "CO_ENTIDADE": inep["code_school"].astype("int64").astype(str),
            "INEP_LATITUDE": inep.geometry.y,
            "INEP_LONGITUDE": inep.geometry.x,
        }
    ).drop_duplicates("CO_ENTIDADE")
    escolas = escolas.merge(inep, on="CO_ENTIDADE", how="left")

    # Origem e ponto plotado
    escolas["ORIGEM"] = ""
    com_cnefe = escolas["STATUS_GEOLOCALIZACAO"].isin(STATUS_CNEFE) & escolas["LATITUDE"].notna()
    so_inep = ~com_cnefe & escolas["INEP_LATITUDE"].notna()
    escolas.loc[com_cnefe, "ORIGEM"] = escolas.loc[com_cnefe, "STATUS_GEOLOCALIZACAO"]
    escolas.loc[so_inep, "ORIGEM"] = "inep"
    escolas.loc[so_inep, "LATITUDE"] = escolas.loc[so_inep, "INEP_LATITUDE"]
    escolas.loc[so_inep, "LONGITUDE"] = escolas.loc[so_inep, "INEP_LONGITUDE"]

    plotadas = escolas[escolas["ORIGEM"] != ""].copy()
    geometrias = pontos(plotadas, "LATITUDE", "LONGITUDE")

    print("Lendo malha municipal (resolucao maxima)...")
    municipios = gpd.read_file("zip://{}".format(ENTRADA_MUNICIPIOS))
    municipios = municipios[municipios["SIGLA_UF"].isin(plotadas["SG_UF"].unique())]
    plotadas["FORA_MUNICIPIO_KM"] = distancia_ao_municipio(geometrias, plotadas["CO_MUNICIPIO"], municipios)
    plotadas["MUNICIPIO_DO_PONTO"] = municipio_do_ponto(geometrias, municipios)

    # Distancia CNEFE x INEP, so quando a escola tem os dois pontos
    ambos = plotadas["ORIGEM"].isin(STATUS_CNEFE) & plotadas["INEP_LATITUDE"].notna()
    dist = geometrias[ambos].to_crs(CRS_METROS).distance(pontos(plotadas[ambos], "INEP_LATITUDE", "INEP_LONGITUDE").to_crs(CRS_METROS))
    plotadas["DIST_CNEFE_INEP_KM"] = (dist / 1000).round(2)
    plotadas.loc[~ambos, ["INEP_LATITUDE", "INEP_LONGITUDE"]] = None

    plotadas = plotadas.rename(columns={"MOTIVO_GEOLOCALIZACAO": "MOTIVO", "ALERTAS_GEOLOCALIZACAO": "ALERTAS"})
    plotadas["CNEFE_NV_GEO_COORD"] = pd.to_numeric(plotadas["CNEFE_NV_GEO_COORD"], errors="coerce").astype("Int64")

    DIR_SAIDA.mkdir(parents=True, exist_ok=True)
    indice = {"ano_censo_escolar": ANO_CENSO_ESCOLAR, "ano_cadastro_inep": "2023", "ufs": {}}

    for uf in sorted(escolas["SG_UF"].unique()):
        da_uf = plotadas[plotadas["SG_UF"] == uf]
        linhas = [[valor_web(v) for v in linha] for linha in da_uf[CAMPOS].astype(object).itertuples(index=False)]
        nome_arquivo = "auditoria_{}_{}.json".format(uf, ANO_CENSO_ESCOLAR)
        caminho = DIR_SAIDA / nome_arquivo
        conteudo = {"uf": uf, "ano_censo_escolar": ANO_CENSO_ESCOLAR, "campos": CAMPOS, "escolas": linhas}
        caminho.write_text(json.dumps(conteudo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

        todas = escolas[escolas["SG_UF"] == uf]
        por_origem = collections.Counter(todas["ORIGEM"].replace("", "sem_ponto"))
        fora = da_uf[da_uf["FORA_MUNICIPIO_KM"] > 0]
        indice["ufs"][uf] = {
            "arquivo": "data/auditoria/" + nome_arquivo,
            "tamanho_bytes": caminho.stat().st_size,
            "total_escolas": len(todas),
            "por_origem": dict(por_origem),
            "fora_do_municipio": dict(collections.Counter(fora["ORIGEM"])),
        }
        print(
            "{}: {} escolas, {} com ponto, por origem {}, fora do municipio {} -> {} ({:.1f} MB)".format(
                uf, len(todas), len(da_uf), dict(por_origem), dict(collections.Counter(fora["ORIGEM"])),
                caminho, caminho.stat().st_size / 1e6,
            )
        )

    caminho_indice = DIR_SAIDA / "indice.json"
    caminho_indice.write_text(json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Indice: {}".format(caminho_indice))


if __name__ == "__main__":
    main()
