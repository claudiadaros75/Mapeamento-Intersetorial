#!/usr/bin/env python3
"""Extrai do CNEFE so os estabelecimentos de ensino (COD_ESPECIE=4), uma UF por vez.

Le o CSV de cada UF *direto de dentro do ZIP* (streaming, sem extrair) e
grava um recorte pequeno em data/ibge_cnefe/escolas/cnefe_escolas_<NN_UF>.csv
(UTF-8, separador ";", so as colunas usadas pelo pareamento). Assim o
pareamento (escolas__parear_inep_cnefe.py) roda em segundos em vez de reler
gigabytes a cada iteracao.

Restricao de disco (ver docs/features/mapa-escolas-inep-cnefe.org, T4): o
CNEFE do Brasil inteiro nao cabe extraido na maquina. Por isso, por padrao,
o ZIP de cada UF e apagado depois do recorte (pode ser rebaixado por
ibge_cnefe__baixar_dados.py). Use --manter-zip para guarda-lo.

Se a UF ja tiver o CSV extraido (ex.: data/ibge_cnefe/zipfiles/35_SP/35_SP.csv
do piloto), ele e lido no lugar do ZIP e nada e baixado nem apagado.

Uso:
    python3 scripts/commands/ibge_cnefe__extrair_escolas.py            # todas as UFs
    python3 scripts/commands/ibge_cnefe__extrair_escolas.py sp rj
    python3 scripts/commands/ibge_cnefe__extrair_escolas.py --manter-zip --forcar ac
"""

import argparse
import csv
import io
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ibge_cnefe__baixar_dados as cnefe_download  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent.parent
DIR_ZIP = RAIZ / "data" / "ibge_cnefe" / "zipfiles"
DIR_SAIDA = RAIZ / "data" / "ibge_cnefe" / "escolas"

# Especie 4 = estabelecimento de ensino (dicionario do CNEFE 2022).
ESPECIE_ENSINO = "4"

COLUNAS = [
    "COD_UNICO_ENDERECO",
    "COD_UF",
    "COD_MUNICIPIO",
    "CEP",
    "DSC_LOCALIDADE",
    "NOM_TIPO_SEGLOGR",
    "NOM_TITULO_SEGLOGR",
    "NOM_SEGLOGR",
    "NUM_ENDERECO",
    "DSC_MODIFICADOR",
    "LATITUDE",
    "LONGITUDE",
    "NV_GEO_COORD",
    "DSC_ESTABELECIMENTO",
]


def abrir_fonte(pacote: str):
    """Abre o CSV da UF: o ja extraido, se existir, senao o de dentro do ZIP. Devolve (texto, zip_ou_None)."""
    extraido = DIR_ZIP / pacote / "{}.csv".format(pacote)
    if extraido.exists():
        print("    lendo CSV ja extraido: {}".format(extraido))
        return open(extraido, encoding="latin-1", newline=""), None

    caminho_zip = DIR_ZIP / "{}.zip".format(pacote)
    pacote_zip = zipfile.ZipFile(caminho_zip)
    nomes_csv = [nome for nome in pacote_zip.namelist() if nome.lower().endswith(".csv")]
    if len(nomes_csv) != 1:
        raise RuntimeError("esperava 1 CSV em {}, achei {}".format(caminho_zip, nomes_csv))
    print("    lendo {} de dentro de {} (sem extrair)".format(nomes_csv[0], caminho_zip.name))
    binario = pacote_zip.open(nomes_csv[0])
    return io.TextIOWrapper(binario, encoding="latin-1", newline=""), pacote_zip


TENTATIVAS = 6


def baixar_com_retentativas(uf: str) -> None:
    """Baixa o ZIP da UF tentando de novo em caso de queda; cada tentativa retoma do .part."""
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            cnefe_download.baixar_uf(uf, com_extracao=False, forcar=False)
            return
        except (OSError, RuntimeError) as erro:  # URLError/timeout sao OSError
            print("\n    tentativa {}/{} falhou: {}".format(tentativa, TENTATIVAS, erro))
            if tentativa == TENTATIVAS:
                raise
            time.sleep(5 * tentativa)


def extrair_uf(uf: str, manter_zip: bool, forcar: bool) -> None:
    """Gera o recorte de escolas de uma UF, baixando o ZIP se preciso e apagando-o ao final."""
    pacote = cnefe_download.UFS[uf]
    saida = DIR_SAIDA / "cnefe_escolas_{}.csv".format(pacote)
    print("[{}] {}".format(uf, pacote))
    if saida.exists() and not forcar:
        print("    ja existe: {}".format(saida))
        return

    caminho_zip = DIR_ZIP / "{}.zip".format(pacote)
    ja_extraido = (DIR_ZIP / pacote / "{}.csv".format(pacote)).exists()
    baixou_agora = False
    if not ja_extraido and not caminho_zip.exists():
        baixar_com_retentativas(uf)
        baixou_agora = True

    inicio = time.time()
    texto, pacote_zip = abrir_fonte(pacote)
    DIR_SAIDA.mkdir(parents=True, exist_ok=True)
    parcial = Path(str(saida) + ".part")
    lidas = gravadas = 0
    try:
        leitor = csv.reader(texto, delimiter=";")
        cabecalho = next(leitor)
        indice = {nome: posicao for posicao, nome in enumerate(cabecalho)}
        faltando = [coluna for coluna in COLUNAS + ["COD_ESPECIE"] if coluna not in indice]
        if faltando:
            raise RuntimeError("colunas ausentes no CNEFE de {}: {}".format(pacote, faltando))
        i_especie = indice["COD_ESPECIE"]
        posicoes = [indice[coluna] for coluna in COLUNAS]

        with open(parcial, "w", encoding="utf-8", newline="") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(COLUNAS)
            for linha in leitor:
                lidas += 1
                if linha[i_especie] == ESPECIE_ENSINO:
                    escritor.writerow([linha[p] for p in posicoes])
                    gravadas += 1
    finally:
        texto.close()
        if pacote_zip is not None:
            pacote_zip.close()
    parcial.rename(saida)
    print(
        "    {} enderecos lidos, {} estabelecimentos de ensino -> {} ({:.0f}s)".format(
            lidas, gravadas, saida.name, time.time() - inicio
        )
    )

    # So apaga ZIP que nao estava extraido; apaga mesmo que ja existisse antes
    # desta execucao, porque a restricao de disco vale para todos.
    if caminho_zip.exists() and not ja_extraido and not manter_zip:
        caminho_zip.unlink()
        print("    ZIP apagado ({}): {}".format("baixado agora" if baixou_agora else "pre-existente", caminho_zip.name))


def principal() -> None:
    """Le a linha de comando e extrai as UFs pedidas (padrao: todas), seguindo para a proxima se uma falhar."""
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument(
        "ufs", nargs="*", choices=list(cnefe_download.UFS) + [[]], type=str.lower,
        help="siglas das UFs (padrao: todas as 27)",
    )
    analisador.add_argument("--manter-zip", action="store_true", help="nao apagar o ZIP depois do recorte")
    analisador.add_argument("--forcar", action="store_true", help="refazer o recorte mesmo que ja exista")
    argumentos = analisador.parse_args()

    falhas = []
    for uf in argumentos.ufs or list(cnefe_download.UFS):
        try:
            extrair_uf(uf, argumentos.manter_zip, argumentos.forcar)
        except Exception as erro:  # segue para a proxima UF; o resumo final lista as falhas
            print("    ERRO em {}: {}".format(uf, erro))
            falhas.append(uf)
    if falhas:
        raise SystemExit("UFs com falha (rode de novo so elas): {}".format(" ".join(falhas)))
    print("todas as UFs extraidas em {}".format(DIR_SAIDA))


if __name__ == "__main__":
    principal()
