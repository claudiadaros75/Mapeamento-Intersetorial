#!/usr/bin/env python3
"""Compara o Catalogo de Escolas do INEP com o Censo Escolar 2025, pelo codigo INEP.

O Censo 2025 nao fornece coordenada nem muda a posicao de nenhuma escola neste
trabalho: as coordenadas vem do Catalogo e sao comparadas as do CNEFE. O Censo so
informa tres situacoes:

    SO_NO_CATALOGO      esta no Catalogo e nao consta no Censo 2025
    SO_NO_CENSO         esta no Censo 2025 e nao consta no Catalogo
    CENSO_SEM_COORD     esta nos dois, mas o Catalogo nao traz coordenada

Entradas:
    data/inep_censo_escolar/zipfiles/microdados_censo_escolar_2025.zip
    web/data/escolas/<UF>.json   (Catalogo + CNEFE, de escolas__gerar_dados_mapa.py)

Saidas em web/data/catalogo_censo_2025/:
    <UF>.json        {"uf", "situacao": {codigo: situacao no Censo}, "so_no_censo": [...]}
                     so_no_censo: [codigo, nome, municipio, situacao]
    index.json       contagens por UF, com a linha BR
    divergencias.csv uma linha por escola nas tres situacoes acima

Situacao no Censo (TP_SITUACAO_FUNCIONAMENTO): 1 em atividade, 2 paralisada, 3 extinta.

Uso:
    .venv/bin/python scripts/commands/catalogo_censo_2025__comparar.py
    .venv/bin/python scripts/commands/catalogo_censo_2025__comparar.py --zip <caminho do zip>
"""

import argparse
import csv
import io
import json
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import censo_escolar_2025__cruzar_catalogo as cruzar  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent.parent
DIR_ESCOLAS = RAIZ / "web" / "data" / "escolas"
DESTINO = RAIZ / "web" / "data" / "catalogo_censo_2025"

UFS = sorted(set(cruzar.UF_POR_CODIGO.values()))
SITUACOES = {"1": "EM_ATIVIDADE", "2": "PARALISADA", "3": "EXTINTA"}
RESTRICOES = {"F": "EM_FUNCIONAMENTO", "P": "PARALISADA", "E": "EXCLUSIVA"}
# Posicoes das colunas em web/data/escolas/<UF>.json, lista "inep".
CODIGO, NOME, LAT, _LON, STATUS, RESTRICAO, IDX_CNEFE, _DIST, _ENDERECO, MUNICIPIO = range(10)


def ler_catalogo() -> dict:
    """Devolve {codigo: (uf, linha inep, lista cnefe da UF)} das 27 UFs."""
    catalogo = {}
    for uf in UFS:
        dados = json.loads((DIR_ESCOLAS / "{}.json".format(uf)).read_text(encoding="utf-8"))
        for linha in dados["inep"]:
            if linha[CODIGO] in catalogo:
                raise SystemExit("codigo INEP repetido no Catalogo: {}".format(linha[CODIGO]))
            catalogo[linha[CODIGO]] = (uf, linha, dados["cnefe"])
    return catalogo


def ler_censo(caminho_zip: Path) -> dict:
    """Devolve {codigo: {"uf", "nome", "municipio", "situacao"}} do Censo 2025."""
    censo = {}
    with zipfile.ZipFile(caminho_zip) as pacote:
        nome_tabela = cruzar.tabela_escola(pacote)
        print("md5 da tabela:", cruzar.conferir_md5(pacote, nome_tabela))
        with pacote.open(nome_tabela) as binario:
            leitor = csv.DictReader(io.TextIOWrapper(binario, encoding="latin-1", newline=""), delimiter=";")
            for linha in leitor:
                codigo = (linha["CO_ENTIDADE"] or "").strip()
                # A escola 43145833 vem sem SG_UF: os dois primeiros digitos do municipio dao a UF.
                uf = (linha["SG_UF"] or "").strip() or cruzar.UF_POR_CODIGO.get((linha["CO_MUNICIPIO"] or "")[:2], "")
                if not codigo or not uf:
                    raise SystemExit("linha do Censo sem codigo ou sem UF: {}".format(linha["CO_ENTIDADE"]))
                if codigo in censo:
                    raise SystemExit("codigo INEP repetido no Censo 2025: {}".format(codigo))
                situacao = (linha["TP_SITUACAO_FUNCIONAMENTO"] or "").strip()
                if situacao not in SITUACOES:
                    raise SystemExit("situacao desconhecida na escola {}: {!r}".format(codigo, situacao))
                censo[codigo] = {"uf": uf, "nome": (linha["NO_ENTIDADE"] or "").strip(),
                                 "municipio": (linha["NO_MUNICIPIO"] or "").strip(), "situacao": situacao}
    return censo


def main():
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument("--zip", type=Path, default=cruzar.ZIP_CENSO, help="zip dos microdados do Censo 2025")
    argumentos = analisador.parse_args()

    catalogo = ler_catalogo()
    censo = ler_censo(argumentos.zip)

    contagem = defaultdict(Counter)
    situacao_por_uf = defaultdict(dict)
    so_no_censo_por_uf = defaultdict(list)
    divergencias = []
    uf_diferente = []

    def somar(uf, chave):
        contagem[uf][chave] += 1
        contagem["BR"][chave] += 1

    for codigo, (uf, linha, cnefe) in catalogo.items():
        somar(uf, "CATALOGO")
        tem_coord = linha[LAT] is not None
        if tem_coord:
            somar(uf, "CATALOGO_COM_COORD")
        par = cnefe[linha[IDX_CNEFE]] if linha[IDX_CNEFE] >= 0 else None
        campos_par = [linha[STATUS], par[2] if par else "", par[3] if par else ""]
        escola = censo.get(codigo)
        if escola is None:
            somar(uf, "SO_NO_CATALOGO")
            if tem_coord:
                somar(uf, "SO_NO_CATALOGO_COM_COORD")
            divergencias.append(["SO_NO_CATALOGO", uf, linha[MUNICIPIO], codigo, linha[NOME],
                                 RESTRICOES[linha[RESTRICAO]], ""] + campos_par)
            continue
        situacao_por_uf[uf][codigo] = int(escola["situacao"])
        somar(uf, "EM_AMBOS")
        somar(uf, "EM_AMBOS_SITUACAO_" + escola["situacao"])
        if escola["uf"] != uf:
            uf_diferente.append((codigo, uf, escola["uf"]))
        if not tem_coord:
            somar(uf, "CENSO_SEM_COORD")
            if escola["situacao"] == "1":
                somar(uf, "CENSO_SEM_COORD_EM_ATIVIDADE")
            if par:
                somar(uf, "CENSO_SEM_COORD_COM_PAR_CNEFE")
            divergencias.append(["CENSO_SEM_COORD", uf, linha[MUNICIPIO], codigo, linha[NOME],
                                 RESTRICOES[linha[RESTRICAO]], SITUACOES[escola["situacao"]]] + campos_par)

    for codigo, escola in censo.items():
        somar(escola["uf"], "CENSO")
        if codigo in catalogo:
            continue
        uf = escola["uf"]
        somar(uf, "SO_NO_CENSO")
        if escola["situacao"] == "1":
            somar(uf, "SO_NO_CENSO_EM_ATIVIDADE")
        so_no_censo_por_uf[uf].append([codigo, escola["nome"], escola["municipio"], int(escola["situacao"])])
        divergencias.append(["SO_NO_CENSO", uf, escola["municipio"], codigo, escola["nome"], "",
                             SITUACOES[escola["situacao"]], "", "", ""])

    # Conferencias: as particoes precisam fechar antes de qualquer arquivo ser gravado.
    br = contagem["BR"]
    if br["EM_AMBOS"] + br["SO_NO_CATALOGO"] != br["CATALOGO"] or br["CATALOGO"] != len(catalogo):
        raise SystemExit("as contagens do Catalogo nao fecham: {}".format(dict(br)))
    if br["EM_AMBOS"] + br["SO_NO_CENSO"] != br["CENSO"] or br["CENSO"] != len(censo):
        raise SystemExit("as contagens do Censo nao fecham: {}".format(dict(br)))
    if len(divergencias) != br["SO_NO_CATALOGO"] + br["SO_NO_CENSO"] + br["CENSO_SEM_COORD"]:
        raise SystemExit("o CSV de divergencias nao fecha com as contagens")

    DESTINO.mkdir(parents=True, exist_ok=True)
    for uf in UFS:
        conteudo = {"uf": uf, "situacao": dict(sorted(situacao_por_uf[uf].items())),
                    "so_no_censo": sorted(so_no_censo_por_uf[uf])}
        (DESTINO / "{}.json".format(uf)).write_text(
            json.dumps(conteudo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    colunas = ["CATALOGO", "CATALOGO_COM_COORD", "CENSO", "EM_AMBOS", "EM_AMBOS_SITUACAO_1", "EM_AMBOS_SITUACAO_2",
               "EM_AMBOS_SITUACAO_3", "SO_NO_CATALOGO", "SO_NO_CATALOGO_COM_COORD", "SO_NO_CENSO",
               "SO_NO_CENSO_EM_ATIVIDADE", "CENSO_SEM_COORD", "CENSO_SEM_COORD_EM_ATIVIDADE",
               "CENSO_SEM_COORD_COM_PAR_CNEFE"]
    resumo = [dict({"UF": uf}, **{c: contagem[uf][c] for c in colunas}) for uf in UFS + ["BR"]]
    (DESTINO / "index.json").write_text(json.dumps({"resumo": resumo}, ensure_ascii=False, indent=1), encoding="utf-8")

    divergencias.sort(key=lambda linha: (linha[0], linha[1], linha[2], linha[3]))
    # utf-8-sig: para o Excel reconhecer os acentos ao abrir o CSV.
    with open(DESTINO / "divergencias.csv", "w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(["CATEGORIA", "UF", "MUNICIPIO", "CODIGO_INEP", "ESCOLA", "SITUACAO_CATALOGO",
                           "SITUACAO_CENSO_2025", "NIVEL_PAR_CNEFE", "LATITUDE_CNEFE", "LONGITUDE_CNEFE"])
        escritor.writerows(divergencias)

    print("Brasil:", {c: br[c] for c in colunas})
    print("escolas com UF diferente entre Catalogo e Censo:", len(uf_diferente), uf_diferente[:10])
    print("gravado em", DESTINO.relative_to(RAIZ))


if __name__ == "__main__":
    main()
