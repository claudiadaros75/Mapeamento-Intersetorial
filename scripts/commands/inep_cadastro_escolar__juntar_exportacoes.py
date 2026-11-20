#!/usr/bin/env python3
"""Junta as exportacoes manuais do Catalogo de Escolas do INEP em uma base so.

O Catalogo de Escolas (painel Oracle Analytics do INEP Data) so exporta
manualmente, pelo navegador, e corta a exportacao em 100.000 linhas. Por
isso o Brasil e exportado em partes (por grande regiao) e salvo em
data/cadastroescolar_inep/*.csv. Este script le todas as partes, confere
que nenhuma bateu no limite, que todas tem as mesmas colunas e que nenhum
codigo INEP se repete, e grava uma base unica.

As colunas sao mantidas como o painel exporta (Latitude/Longitude sao o
ponto do proprio INEP). Entra uma
coluna a mais, "Arquivo de origem", com o nome da parte de onde veio cada
linha.

Uso:
    .venv/bin/python scripts/commands/inep_cadastro_escolar__juntar_exportacoes.py
    .venv/bin/python ... --entrada <pasta> --saida <arquivo.csv>
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent.parent
ENTRADA = RAIZ / "data" / "cadastroescolar_inep"
SAIDA = RAIZ / "data" / "inep_catalogo_escolas.csv"

# O painel corta a exportacao aqui; uma parte com esse tamanho esta truncada.
LIMITE_EXPORTACAO = 100_000

CODIGO = "Código INEP"


def ler_parte(arquivo: Path) -> pd.DataFrame:
    parte = pd.read_csv(arquivo, dtype=str, encoding="utf-8-sig", keep_default_na=False)
    # Escola sem ponto vem com Latitude/Longitude so de espacos; tira espacos das pontas de tudo.
    parte = parte.apply(lambda coluna: coluna.str.strip())
    parte["Arquivo de origem"] = arquivo.name
    return parte


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--entrada", type=Path, default=ENTRADA)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    args = parser.parse_args()

    arquivos = sorted(args.entrada.glob("*.csv"))
    if not arquivos:
        print("Nenhum CSV em {}".format(args.entrada), file=sys.stderr)
        return 1

    partes, erros = [], []
    for arquivo in arquivos:
        parte = ler_parte(arquivo)
        print("  {:>7,} escolas  {}".format(len(parte), arquivo.name).replace(",", "."))
        if len(parte) >= LIMITE_EXPORTACAO - 1:
            erros.append("{} tem {} linhas: exportacao truncada pelo painel".format(arquivo.name, len(parte)))
        if partes and list(parte.columns) != list(partes[0].columns):
            erros.append("{} tem colunas diferentes de {}".format(arquivo.name, arquivos[0].name))
        partes.append(parte)

    base = pd.concat(partes, ignore_index=True)

    repetidos = base[base[CODIGO].duplicated(keep=False)]
    if not repetidos.empty:
        erros.append("{} codigos INEP aparecem em mais de uma linha, ex.: {}".format(
            repetidos[CODIGO].nunique(), ", ".join(repetidos[CODIGO].unique()[:5])))
    if erros:
        for erro in erros:
            print("ERRO: " + erro, file=sys.stderr)
        return 1

    base = base.sort_values(["UF", CODIGO], key=lambda s: s.str.zfill(8) if s.name == CODIGO else s)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    base.to_csv(args.saida, index=False, encoding="utf-8")

    com_ponto = ((base["Latitude"] != "") & (base["Longitude"] != "")).sum()
    print("Total: {:,} escolas em {} UFs; {:,} com latitude/longitude".format(
        len(base), base["UF"].nunique(), com_ponto).replace(",", "."))
    print("Gravado em {}".format(args.saida.relative_to(RAIZ) if args.saida.is_relative_to(RAIZ) else args.saida))
    return 0


if __name__ == "__main__":
    sys.exit(main())
