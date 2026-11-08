#!/usr/bin/env python3
"""Baixa o Catalogo de Escolas do INEP (com latitude/longitude) do Google Drive do projeto.

O Catalogo de Escolas (INEP Data) e a unica fonte do INEP que traz a
coordenada de cada escola; os microdados do Censo Escolar nao trazem. O
arquivo "unificado" e a uniao das 5 exportacoes regionais do painel
"Analise - Tabela da lista das escolas - Detalhado" (ver
docs/features/mapa-escolas-inep-cnefe.org, T1/D1), publicada numa pasta
compartilhada do Drive por link.

Formato: CSV UTF-8 com BOM, separador ",", 19 colunas (Escola, Codigo
INEP, UF, Municipio, Endereco, ..., Latitude, Longitude).

Uso:
    python3 scripts/commands/inep_catalogo_escolas__baixar_dados.py
    python3 scripts/commands/inep_catalogo_escolas__baixar_dados.py --forcar
"""

import argparse
import urllib.request
from pathlib import Path

# Pasta do Drive: https://drive.google.com/drive/folders/1i76SVcveDhI7DuvCQLhEJRsUgMxaSKia
ID_DRIVE = "1AYJVIYVhhOqzrMwedxFlHoe6Mj5cQEvr"
URL = "https://drive.usercontent.google.com/download?id={}&export=download&confirm=t".format(ID_DRIVE)

DESTINO = (
    Path(__file__).resolve().parent.parent.parent
    / "data" / "inep_catalogo_escolas" / "catalogo-escolas-unificado.csv"
)
# Tamanho conferido em 2026-11-07; serve para detectar download truncado
# ou pagina HTML de erro do Drive no lugar do CSV.
TAMANHO_ESPERADO = 85_660_100
CABECALHO_ESPERADO = "Restrição de Atendimento,Escola,Código INEP"
BLOCO = 1024 * 1024


def baixar(destino: Path) -> None:
    """Baixa o CSV para <destino>.part e so renomeia depois de validar tamanho e cabecalho."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = Path(str(destino) + ".part")
    requisicao = urllib.request.Request(URL, headers={"User-Agent": "georef-artifacts"})
    with urllib.request.urlopen(requisicao) as resposta, open(parcial, "wb") as saida:
        recebido = 0
        while True:
            bloco = resposta.read(BLOCO)
            if not bloco:
                break
            saida.write(bloco)
            recebido += len(bloco)
            print("\r    {:.1f} MB".format(recebido / 1024 / 1024), end="", flush=True)
    print()

    with open(parcial, encoding="utf-8-sig") as arquivo:
        primeira_linha = arquivo.readline()
    if not primeira_linha.startswith(CABECALHO_ESPERADO):
        raise RuntimeError("o Drive nao devolveu o CSV esperado (cabecalho: {!r})".format(primeira_linha[:80]))
    if parcial.stat().st_size != TAMANHO_ESPERADO:
        print(
            "    AVISO: tamanho {} difere do conferido em 2026-11-07 ({}) - o arquivo do Drive "
            "pode ter sido atualizado".format(parcial.stat().st_size, TAMANHO_ESPERADO)
        )
    parcial.rename(destino)


def principal() -> None:
    """Le a linha de comando e baixa o catalogo, reaproveitando o arquivo se ja existir."""
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument("--forcar", action="store_true", help="rebaixar mesmo que o arquivo ja exista")
    argumentos = analisador.parse_args()

    if DESTINO.exists() and not argumentos.forcar:
        print("ja baixado: {} ({} bytes)".format(DESTINO, DESTINO.stat().st_size))
        return
    print("GET {}".format(URL))
    baixar(DESTINO)
    print("OK: {} ({} bytes)".format(DESTINO, DESTINO.stat().st_size))


if __name__ == "__main__":
    principal()
