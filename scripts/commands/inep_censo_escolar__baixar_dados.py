#!/usr/bin/env python3
"""Baixa os microdados do Censo Escolar (INEP), um ZIP por ano.

Todos os anos de 1995 a 2025 seguem o mesmo padrao de URL em
download.inep.gov.br/dados_abertos/; 2025 e a unica excecao conhecida, com
um "_" antes do ".zip" (ver NOMES_REMOTOS). Cada ZIP traz, dentro da pasta
"dados/", um ou mais CSVs de microdados e um "md5_*.txt" com o hash
publicado de cada um - o script confere esse hash apos extrair.

O plano do projeto (docs/05-plano-marcadores-escolas-inep.org) decidiu usar
so 2024 para a v1 do recurso de marcadores de escolas; este script baixa
todos os anos por padrao mesmo assim, para deixar o historico completo
disponivel em disco de uma vez.

Uso:
    .venv/bin/python scripts/commands/inep_censo_escolar__baixar_dados.py
    .venv/bin/python ... 2024 2025 --extrair
    .venv/bin/python ... --listar
"""

import argparse
import hashlib
import re
import ssl
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BASE_URL = "https://download.inep.gov.br/dados_abertos"

# download.inep.gov.br nao envia a CA intermediaria no handshake TLS (visto
# com "openssl s_client -showcerts": so a folha, sem a "RNP ICPEdu GR46 OV
# TLS CA 2025") - por isso a verificacao padrao falha com "unable to get
# local issuer certificate" mesmo o certificado sendo valido. Em vez de
# desabilitar a verificacao, buscamos essa CA intermediaria (URL fixa do
# campo Authority Information Access do certificado da folha) e a
# acrescentamos as CAs confiaveis.
URL_CA_INTERMEDIARIA = "http://secure.globalsign.com/cacert/rnpicpedugr46ovtlsca2025.crt"

_ABRIDOR = None


def abridor_https() -> urllib.request.OpenerDirector:
    """Devolve (e cacheia) um abridor urllib que confia na CA intermediaria do INEP."""
    global _ABRIDOR
    if _ABRIDOR is None:
        contexto = ssl.create_default_context()
        with urllib.request.urlopen(URL_CA_INTERMEDIARIA, timeout=15) as resposta:
            contexto.load_verify_locations(cadata=resposta.read())
        _ABRIDOR = urllib.request.build_opener(urllib.request.HTTPSHandler(context=contexto))
    return _ABRIDOR

DESTINO = Path(__file__).resolve().parent.parent.parent / "data" / "inep_censo_escolar" / "zipfiles"

BLOCO = 1024 * 1024

ANOS = [str(ano) for ano in range(1995, 2026)]

# ano -> nome do arquivo no servidor, quando difere do padrao
# "microdados_censo_escolar_<ano>.zip". Unica excecao conhecida ate agora.
NOMES_REMOTOS = {
    "2025": "microdados_censo_escolar_2025_.zip",
}

NOME_MD5 = re.compile(r"^md5.*\.txt$", re.IGNORECASE)


def nome_remoto(ano: str) -> str:
    """Nome do arquivo ZIP no servidor para um ano (padrao ou excecao)."""
    return NOMES_REMOTOS.get(ano, "microdados_censo_escolar_{}.zip".format(ano))


def mb(bytes_: int) -> str:
    """Formata um tamanho em bytes como texto em megabytes.

    Serve so para o relatorio impresso na tela. Ex.: 7000265 -> "6.7 MB".
    """
    return "{:.1f} MB".format(bytes_ / (1024 * 1024))


def tamanho_remoto(url: str) -> int:
    """Devolve o Content-Length do arquivo remoto, ou 0 se indisponivel."""
    try:
        requisicao = urllib.request.Request(url, method="HEAD")
        with abridor_https().open(requisicao, timeout=15) as resposta:
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

    with abridor_https().open(requisicao) as resposta:
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


def conferir_md5(pasta: Path) -> None:
    """Confere os hashes MD5 publicados dentro de um "md5*.txt" da pasta extraida.

    O arquivo de hashes fica em "dados/" e lista "<hash> *<arquivo>", um CSV
    por linha (formato md5sum). Arquivos sem correspondencia no ZIP, ou sem
    nenhum md5*.txt encontrado, so geram aviso - nao interrompem o script.
    """
    arquivos_md5 = list(pasta.rglob("md5*.txt")) + [p for p in pasta.rglob("*.txt") if NOME_MD5.match(p.name)]
    arquivos_md5 = sorted(set(arquivos_md5))
    if not arquivos_md5:
        print("    aviso: nenhum md5*.txt encontrado, hash nao conferido")
        return

    for arquivo_md5 in arquivos_md5:
        for linha in arquivo_md5.read_text(encoding="utf-8", errors="replace").splitlines():
            linha = linha.strip()
            if not linha:
                continue
            hash_esperado, nome_csv = linha.split(maxsplit=1)
            nome_csv = nome_csv.lstrip("*").strip()
            caminho_csv = arquivo_md5.parent / nome_csv
            if not caminho_csv.exists():
                print("    aviso: {} referenciado em {} nao encontrado".format(nome_csv, arquivo_md5.name))
                continue

            hash_real = hashlib.md5()
            with open(caminho_csv, "rb") as arquivo:
                for bloco in iter(lambda: arquivo.read(BLOCO), b""):
                    hash_real.update(bloco)

            if hash_real.hexdigest().lower() == hash_esperado.lower():
                print("    md5 OK: {}".format(nome_csv))
            else:
                print(
                    "    aviso: md5 DIVERGENTE em {} (esperado {}, obtido {})".format(
                        nome_csv, hash_esperado, hash_real.hexdigest()
                    )
                )


def extrair(arquivo_zip: Path) -> Path:
    """Extrai o ZIP em data/inep_censo_escolar/zipfiles/<ano>/ e devolve a pasta."""
    pasta = arquivo_zip.parent / arquivo_zip.stem
    with zipfile.ZipFile(arquivo_zip) as pacote:
        pacote.extractall(pasta)
    print("    extraido em {}".format(pasta))
    conferir_md5(pasta)
    return pasta


def baixar_ano(ano: str, com_extracao: bool, forcar: bool) -> None:
    """Garante o ZIP de um ano em data/inep_censo_escolar/zipfiles/, baixando-o se for preciso.

    Um arquivo ja presente e reaproveitado, a menos que o tamanho divirja do
    servidor - sinal de download truncado - ou que forcar seja verdadeiro.
    Com com_extracao, descompacta o pacote ao final e confere o md5.
    """
    url = "{}/{}".format(BASE_URL, nome_remoto(ano))
    destino = DESTINO / "microdados_censo_escolar_{}.zip".format(ano)

    print("[{}] {}".format(ano, url))

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
    """Le a linha de comando e baixa os anos pedidos (padrao: todos, 1995-2025)."""
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument(
        "anos",
        nargs="*",
        choices=ANOS + [[]],
        default=ANOS,
        help="anos a baixar (padrao: todos, 1995-2025)",
    )
    analisador.add_argument(
        "--extrair",
        action="store_true",
        help="descompactar cada ZIP em data/inep_censo_escolar/zipfiles/<ano>/ e conferir o md5",
    )
    analisador.add_argument(
        "--forcar",
        action="store_true",
        help="rebaixar mesmo que o arquivo ja exista",
    )
    analisador.add_argument("--listar", action="store_true", help="lista os anos e URLs e sai")
    argumentos = analisador.parse_args()

    if argumentos.listar:
        for ano in ANOS:
            print("{}  {}/{}".format(ano, BASE_URL, nome_remoto(ano)))
        return

    for ano in argumentos.anos:
        baixar_ano(ano, argumentos.extrair, argumentos.forcar)


if __name__ == "__main__":
    principal()
