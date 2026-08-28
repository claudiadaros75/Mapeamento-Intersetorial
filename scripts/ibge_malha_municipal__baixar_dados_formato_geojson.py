#!/usr/bin/env python3
"""Baixa as malhas territoriais do IBGE em GeoJSON pela API de Malhas (v4).

Cobre os mesmos seis recortes distribuidos em shapefile na pasta Brasil/ da
Malha Municipal Digital 2024, mas ja no formato GeoJSON, pronto para uso em
mapas web (Leaflet, MapLibre, GitHub Pages).

As feicoes devolvidas pela API trazem apenas a propriedade "codarea". Por
padrao o script complementa cada feicao com nome, sigla e codigos dos
recortes superiores, consultando a API de Localidades (v1).

Uso:
    .venv/bin/python scripts/ibge_malha_municipal__baixar_dados_formato_geojson.py
    .venv/bin/python ... uf municipios --qualidade maxima
    .venv/bin/python ... --listar
"""

import argparse
import gzip
import json
import urllib.parse
import urllib.request
from pathlib import Path

API_MALHAS = "https://servicodados.ibge.gov.br/api/v4/malhas/paises/BR"
API_LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades"
GEOJSON = "application/vnd.geo+json"

DESTINO = Path(__file__).resolve().parent.parent / "data" / "geojson"

QUALIDADES = ("minima", "intermediaria", "maxima")

# nivel -> (intrarregiao na API de malhas, recurso na API de localidades,
#           equivalente em shapefile na MMD 2024)
NIVEIS = {
    "pais": (None, None, "BR_Pais_2024"),
    "regioes": ("regiao", "regioes", "BR_Regioes_2024"),
    "uf": ("UF", "estados", "BR_UF_2024"),
    "intermediarias": ("regiao-intermediaria", "regioes-intermediarias", "BR_RG_Intermediarias_2024"),
    "imediatas": ("regiao-imediata", "regioes-imediatas", "BR_RG_Imediatas_2024"),
    "municipios": ("municipio", "municipios", "BR_Municipios_2024"),
}


def obter(url: str) -> bytes:
    """Faz GET em url e devolve o corpo, descomprimindo se vier em gzip."""
    requisicao = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(requisicao) as resposta:
        corpo = resposta.read()
    # A API de Malhas responde em gzip mesmo sem negociacao; o urllib nao
    # descomprime sozinho, e sem este passo o .geojson sai ilegivel.
    if corpo[:2] == b"\x1f\x8b":
        corpo = gzip.decompress(corpo)
    return corpo


def url_malha(intrarregiao: str, qualidade: str) -> str:
    """Monta a URL da API de Malhas para um recorte e um nivel de qualidade.

    Sem intrarregiao a API devolve apenas o contorno do Brasil; com ela,
    devolve o pais subdividido naquele recorte (UF, municipio etc.).
    """
    parametros = {"qualidade": qualidade, "formato": GEOJSON}
    if intrarregiao:
        parametros["intrarregiao"] = intrarregiao
    return "{}?{}".format(API_MALHAS, urllib.parse.urlencode(parametros))


def achatar(localidade: dict) -> dict:
    """Reduz o objeto aninhado da API de Localidades a propriedades simples.

    Ex.: {"id": 3513009, "nome": "Cotia", "regiao-imediata": {...}} vira
    {"nome": "Cotia", "cd_uf": "35", "nm_uf": "Sao Paulo", ...}.
    """
    propriedades = {"nome": localidade["nome"]}
    if "sigla" in localidade:
        propriedades["sigla"] = localidade["sigla"]

    intermediaria = localidade.get("regiao-intermediaria") or (
        (localidade.get("regiao-imediata") or {}).get("regiao-intermediaria")
    )
    if intermediaria:
        propriedades["cd_rg_intermediaria"] = str(intermediaria["id"])
        propriedades["nm_rg_intermediaria"] = intermediaria["nome"]

    imediata = localidade.get("regiao-imediata")
    if imediata:
        propriedades["cd_rg_imediata"] = str(imediata["id"])
        propriedades["nm_rg_imediata"] = imediata["nome"]

    uf = localidade.get("UF") or (intermediaria or {}).get("UF")
    if uf:
        propriedades["cd_uf"] = str(uf["id"])
        propriedades["nm_uf"] = uf["nome"]
        propriedades["sigla_uf"] = uf["sigla"]

    regiao = localidade.get("regiao") or (uf or {}).get("regiao")
    if regiao:
        propriedades["cd_regiao"] = str(regiao["id"])
        propriedades["nm_regiao"] = regiao["nome"]
        propriedades["sigla_regiao"] = regiao["sigla"]

    return propriedades


def tabela_nomes(recurso: str) -> dict:
    """Devolve {codigo: propriedades} para um recorte da API de Localidades."""
    dados = json.loads(obter("{}/{}".format(API_LOCALIDADES, recurso)))
    return {str(item["id"]): achatar(item) for item in dados}


def baixar_nivel(nivel: str, qualidade: str, com_nomes: bool) -> Path:
    """Baixa a malha de um recorte e grava em data/geojson/.

    Com com_nomes, cada feicao ganha nome, sigla e codigos dos recortes
    superiores vindos da API de Localidades; sem ele, fica apenas o codarea
    que a API de Malhas devolve. Feicoes sem correspondencia em Localidades
    sao mantidas como vieram, e o total delas e avisado na tela.

    Devolve o caminho do arquivo gravado.
    """
    intrarregiao, recurso, equivalente = NIVEIS[nivel]

    print("[{}] equivalente a {}.zip, qualidade {}".format(nivel, equivalente, qualidade))
    url = url_malha(intrarregiao, qualidade)
    print("  GET {}".format(url))
    malha = json.loads(obter(url))

    if com_nomes and recurso:
        nomes = tabela_nomes(recurso)
        sem_nome = 0
        for feicao in malha["features"]:
            codigo = feicao["properties"]["codarea"]
            complemento = nomes.get(codigo)
            if complemento is None:
                sem_nome += 1
                continue
            feicao["properties"].update(complemento)
        if sem_nome:
            print("  aviso: {} feicoes sem correspondencia em localidades".format(sem_nome))
    elif com_nomes:
        malha["features"][0]["properties"].update({"nome": "Brasil", "sigla": "BR"})

    DESTINO.mkdir(parents=True, exist_ok=True)
    saida = DESTINO / "BR_{}_2024_{}.geojson".format(nivel, qualidade)
    with open(saida, "w", encoding="utf-8") as arquivo:
        json.dump(malha, arquivo, ensure_ascii=False)

    tamanho_mb = saida.stat().st_size / (1024 * 1024)
    print("  OK: {} feicoes -> {} ({:.1f} MB)".format(len(malha["features"]), saida, tamanho_mb))
    return saida


def principal() -> None:
    """Le a linha de comando e baixa os recortes pedidos (padrao: todos)."""
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument(
        "niveis",
        nargs="*",
        choices=list(NIVEIS) + [[]],
        default=list(NIVEIS),
        help="recortes a baixar (padrao: todos)",
    )
    analisador.add_argument("--qualidade", choices=QUALIDADES, default="minima")
    analisador.add_argument(
        "--sem-nomes",
        action="store_true",
        help="nao consultar a API de Localidades; mantem apenas codarea",
    )
    analisador.add_argument("--listar", action="store_true", help="lista os recortes e sai")
    argumentos = analisador.parse_args()

    if argumentos.listar:
        for nivel, (_, _, equivalente) in NIVEIS.items():
            print("{:16s} {}.zip".format(nivel, equivalente))
        return

    for nivel in argumentos.niveis:
        baixar_nivel(nivel, argumentos.qualidade, not argumentos.sem_nomes)


if __name__ == "__main__":
    principal()
