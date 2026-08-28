#!/usr/bin/env python3
"""Baixa as malhas territoriais do IBGE em shapefile pelo FTP de geociencias.

Contraparte de ibge_malha_municipal__baixar_dados_formato_geojson.py, com os
mesmos seis recortes e a mesma interface de linha de comando. A diferenca
esta na fonte e na finalidade:

- shapefile (este script): tabela de atributos completa, inclusive AREA_KM2,
  em SIRGAS 2000 (EPSG:4674) e sem generalizacao. E a fonte para analise em
  geopandas. Estes dados não estão disponiveis nos geojsons
- GeoJSON (o outro script): geometria generalizada e pronta para mapas web.

Uso:
    .venv/bin/python scripts/ibge_malha_municipal__baixar_dados_formato_shapefile.py
    .venv/bin/python ... uf municipios --extrair
    .venv/bin/python ... --listar
"""

import argparse
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BASE_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais"
    "/malhas_municipais/municipio_2024/Brasil"
)

DESTINO = Path(__file__).resolve().parent.parent / "data"

BLOCO = 1024 * 1024

# nivel -> (pacote no FTP, feicoes esperadas)
# As chaves sao as mesmas do script de GeoJSON, para que os dois recortes
# possam ser pedidos pelo mesmo nome.
NIVEIS = {
    "pais": ("BR_Pais_2024", 1),
    "regioes": ("BR_Regioes_2024", 5),
    "uf": ("BR_UF_2024", 27),
    "intermediarias": ("BR_RG_Intermediarias_2024", 133),
    "imediatas": ("BR_RG_Imediatas_2024", 510),
    "municipios": ("BR_Municipios_2024", 5571),
}


def mb(bytes_: int) -> str:
    """Formata um tamanho em bytes como texto em megabytes.

    Serve so para o relatorio impresso na tela. Ex.: 7000265 -> "6.7 MB".
    """
    return "{:.1f} MB".format(bytes_ / (1024 * 1024))


def tamanho_remoto(url: str) -> int:
    """Devolve o Content-Length do arquivo remoto, ou 0 se indisponivel."""
    try:
        requisicao = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(requisicao) as resposta:
            return int(resposta.headers.get("Content-Length") or 0)
    except (urllib.error.URLError, ValueError):
        return 0


def baixar(url: str, destino: Path) -> None:
    """Baixa url para destino, retomando de um download parcial se houver.

    O corpo vai para um arquivo <destino>.part, renomeado para destino so
    quando o download termina inteiro - assim um ZIP truncado nunca ocupa o
    nome final. Se o .part ja existir, pede a continuacao com o cabecalho
    Range; caso o servidor ignore o pedido e mande o arquivo inteiro, o
    .part e reescrito do zero em vez de receber os bytes por acrescimo, que
    produziria um ZIP corrompido.

    Levanta RuntimeError se o download nao produzir dados ou terminar com
    tamanho diferente do anunciado pelo servidor; nos dois casos o .part e
    preservado para uma nova tentativa.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = Path(str(destino) + ".part")

    ja_baixado = parcial.stat().st_size if parcial.exists() else 0
    cabecalho = {"Range": "bytes={}-".format(ja_baixado)} if ja_baixado else {}
    requisicao = urllib.request.Request(url, headers=cabecalho)

    with urllib.request.urlopen(requisicao) as resposta:
        # Se pedimos a retomada mas o servidor devolveu 200, ele ignorou o
        # Range e esta mandando o arquivo inteiro: recomecar, nao acrescentar.
        retomando = resposta.status == 206
        if ja_baixado and not retomando:
            print("    servidor ignorou a retomada, recomecando do zero")
            ja_baixado = 0

        total = int(resposta.headers.get("Content-Length") or 0) + ja_baixado
        modo = "ab" if retomando else "wb"
        recebido = ja_baixado

        with open(parcial, modo) as saida:
            while True:
                bloco = resposta.read(BLOCO)
                if not bloco:
                    break
                saida.write(bloco)
                recebido += len(bloco)
                if total:
                    print(
                        "\r    {} / {} ({:.0f}%)".format(mb(recebido), mb(total), 100 * recebido / total),
                        end="",
                        flush=True,
                    )
        if total:
            print()

    if not parcial.exists() or parcial.stat().st_size == 0:
        raise RuntimeError("download nao produziu dados para {}".format(destino))
    if total and parcial.stat().st_size != total:
        raise RuntimeError(
            "download incompleto de {}: {} de {} bytes (o .part foi mantido "
            "para retomar)".format(destino.name, parcial.stat().st_size, total)
        )
    parcial.rename(destino)


def extrair(arquivo_zip: Path) -> Path:
    """Extrai o ZIP em data/<nome_do_pacote>/ e devolve a pasta."""
    pasta = arquivo_zip.parent / arquivo_zip.stem
    with zipfile.ZipFile(arquivo_zip) as pacote:
        pacote.extractall(pasta)
    componentes = sorted(caminho.suffix for caminho in pasta.iterdir())
    print("    extraido em {} ({})".format(pasta, " ".join(componentes)))
    return pasta


def baixar_nivel(nivel: str, com_extracao: bool, forcar: bool) -> None:
    """Garante o ZIP de um recorte em data/, baixando-o se for preciso.

    Um arquivo ja presente e reaproveitado, a menos que o tamanho divirja do
    servidor - sinal de download truncado - ou que forcar seja verdadeiro.
    Com com_extracao, descompacta o pacote ao final.
    """
    pacote, feicoes = NIVEIS[nivel]
    url = "{}/{}.zip".format(BASE_URL, pacote)
    destino = DESTINO / "{}.zip".format(pacote)

    print("[{}] {}.zip - {} feicoes".format(nivel, pacote, feicoes))

    if destino.exists() and not forcar:
        local = destino.stat().st_size
        remoto = tamanho_remoto(url)
        if remoto and local != remoto:
            print("    tamanho difere do servidor ({} vs {}), rebaixando".format(mb(local), mb(remoto)))
            destino.unlink()
        else:
            print("    ja baixado: {} ({})".format(destino, mb(local)))
            if com_extracao:
                extrair(destino)
            return

    print("    GET {}".format(url))
    baixar(url, destino)
    print("    OK: {} ({})".format(destino, mb(destino.stat().st_size)))
    if com_extracao:
        extrair(destino)


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
    analisador.add_argument(
        "--extrair",
        action="store_true",
        help="descompactar o ZIP em data/<pacote>/ apos o download",
    )
    analisador.add_argument(
        "--forcar",
        action="store_true",
        help="rebaixar mesmo que o arquivo ja exista",
    )
    analisador.add_argument("--listar", action="store_true", help="lista os recortes e sai")
    argumentos = analisador.parse_args()

    if argumentos.listar:
        for nivel, (pacote, feicoes) in NIVEIS.items():
            print("{:16s} {:28s} {:5d} feicoes".format(nivel, pacote + ".zip", feicoes))
        return

    for nivel in argumentos.niveis:
        baixar_nivel(nivel, argumentos.extrair, argumentos.forcar)


if __name__ == "__main__":
    principal()
