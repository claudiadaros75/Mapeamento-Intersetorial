#!/usr/bin/env python3
"""Baixa o CNEFE (Censo Demografico 2022) do IBGE, um ZIP por UF.

O Cadastro Nacional de Enderecos para Fins Estatisticos (CNEFE) traz, desde
o Censo 2022, latitude/longitude por endereco - inclusive de
estabelecimentos de ensino (COD_ESPECIE = 4). E a fonte usada para dar
geolocalizacao exata as escolas do Censo Escolar do INEP (ver
docs/06-georeferenciamento-escolas.org).

Cada ZIP de UF contem um CSV unico com todos os enderecos do estado - sem
filtro por tipo de estabelecimento; esse filtro fica para um script de ETL
separado (ver docs/06-georeferenciamento-escolas.org, "Proximos passos").
Nao ha checksum publicado pelo IBGE para esses arquivos, ao contrario dos
ZIPs do INEP.

Uso:
    .venv/bin/python scripts/commands/ibge_cnefe__baixar_dados.py sp
    .venv/bin/python scripts/commands/ibge_cnefe__baixar_dados.py --extrair
    .venv/bin/python ... --listar
"""

import argparse
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BASE_URL = (
    "https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos"
    "/Censo_Demografico_2022/Arquivos_CNEFE/CSV/UF"
)

DESTINO = Path(__file__).resolve().parent.parent.parent / "data" / "ibge_cnefe" / "zipfiles"

BLOCO = 1024 * 1024

# sigla (minuscula, usada na linha de comando) -> nome do pacote no FTP
UFS = {
    "ro": "11_RO",
    "ac": "12_AC",
    "am": "13_AM",
    "rr": "14_RR",
    "pa": "15_PA",
    "ap": "16_AP",
    "to": "17_TO",
    "ma": "21_MA",
    "pi": "22_PI",
    "ce": "23_CE",
    "rn": "24_RN",
    "pb": "25_PB",
    "pe": "26_PE",
    "al": "27_AL",
    "se": "28_SE",
    "ba": "29_BA",
    "mg": "31_MG",
    "es": "32_ES",
    "rj": "33_RJ",
    "sp": "35_SP",
    "pr": "41_PR",
    "sc": "42_SC",
    "rs": "43_RS",
    "ms": "50_MS",
    "mt": "51_MT",
    "go": "52_GO",
    "df": "53_DF",
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
    """Extrai o ZIP em data/ibge_cnefe/zipfiles/<uf>/ e devolve a pasta."""
    pasta = arquivo_zip.parent / arquivo_zip.stem
    with zipfile.ZipFile(arquivo_zip) as pacote:
        pacote.extractall(pasta)
    componentes = sorted(caminho.name for caminho in pasta.iterdir())
    print("    extraido em {} ({})".format(pasta, ", ".join(componentes)))
    return pasta


def baixar_uf(uf: str, com_extracao: bool, forcar: bool) -> None:
    """Garante o ZIP de uma UF em data/ibge_cnefe/zipfiles/, baixando-o se for preciso.

    Um arquivo ja presente e reaproveitado, a menos que o tamanho divirja do
    servidor - sinal de download truncado - ou que forcar seja verdadeiro.
    Com com_extracao, descompacta o pacote ao final. O IBGE nao publica
    checksum para estes arquivos, entao nao ha conferencia de integridade
    alem do tamanho.
    """
    pacote = UFS[uf]
    url = "{}/{}.zip".format(BASE_URL, pacote)
    destino = DESTINO / "{}.zip".format(pacote)

    print("[{}] {}.zip".format(uf, pacote))

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
    """Le a linha de comando e baixa as UFs pedidas (padrao: todas as 27)."""
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument(
        "ufs",
        nargs="*",
        choices=list(UFS) + [[]],
        default=list(UFS),
        type=str.lower,
        help="siglas das UFs a baixar (padrao: todas)",
    )
    analisador.add_argument(
        "--extrair",
        action="store_true",
        help="descompactar o ZIP em data/ibge_cnefe/zipfiles/<pacote>/ apos o download",
    )
    analisador.add_argument(
        "--forcar",
        action="store_true",
        help="rebaixar mesmo que o arquivo ja exista",
    )
    analisador.add_argument("--listar", action="store_true", help="lista as UFs e sai")
    argumentos = analisador.parse_args()

    if argumentos.listar:
        for uf, pacote in UFS.items():
            print("{:4s} {}.zip".format(uf, pacote))
        return

    for uf in argumentos.ufs:
        baixar_uf(uf, argumentos.extrair, argumentos.forcar)


if __name__ == "__main__":
    principal()
