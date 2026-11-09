#!/usr/bin/env python3
"""Traz o Censo Escolar 2025 (todas as UFs) e mede quais escolas tem coordenada.

Os microdados do Censo nao trazem latitude/longitude. Por isso cada escola de
2025 e procurada, pelo codigo INEP, na nossa copia do Catalogo de Escolas (que
corresponde ao Censo 2024, ver docs/11-censo-escolar-x-cnefe.org) e no
pareamento com o CNEFE.

Entradas:
    data/inep_censo_escolar/zipfiles/microdados_censo_escolar_2025.zip
    data/inep_catalogo_escolas/catalogo-escolas-unificado.csv
    data/escolas_pareamento/pares.csv

Saidas em data/censo_escolar_2025/:
    escolas_censo_2025_coordenadas.csv  uma linha por escola do Censo 2025
    resumo_por_uf.csv                   contagens por UF, com a linha BR

Categoria de cada escola (COORDENADA_CATALOGO):
    COM_COORDENADA  no catalogo, com latitude e longitude
    SEM_COORDENADA  no catalogo, sem latitude e longitude
    FORA_DO_CATALOGO  codigo INEP ausente do catalogo

Uso:
    .venv/bin/python scripts/commands/censo_escolar_2025__cruzar_catalogo.py
"""

import csv
import hashlib
import io
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
ZIP_CENSO = RAIZ / "data" / "inep_censo_escolar" / "zipfiles" / "microdados_censo_escolar_2025.zip"
CATALOGO = RAIZ / "data" / "inep_catalogo_escolas" / "catalogo-escolas-unificado.csv"
PARES = RAIZ / "data" / "escolas_pareamento" / "pares.csv"
DESTINO = RAIZ / "data" / "censo_escolar_2025"

COLUNAS_CENSO = ["CO_ENTIDADE", "NO_ENTIDADE", "SG_UF", "CO_MUNICIPIO", "NO_MUNICIPIO", "TP_DEPENDENCIA",
                 "TP_LOCALIZACAO", "TP_SITUACAO_FUNCIONAMENTO"]
CATEGORIAS = ["COM_COORDENADA", "SEM_COORDENADA", "FORA_DO_CATALOGO"]
# A escola 43145833 vem sem SG_UF nos microdados; os dois primeiros digitos do
# codigo do municipio (IBGE) identificam a UF.
UF_POR_CODIGO = {"11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO", "21": "MA",
                 "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA",
                 "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
                 "51": "MT", "52": "GO", "53": "DF"}


def ler_catalogo() -> dict:
    with open(CATALOGO, encoding="utf-8-sig", newline="") as arquivo:
        return {linha["Código INEP"].strip(): linha for linha in csv.DictReader(arquivo)}


def ler_pares() -> dict:
    with open(PARES, encoding="utf-8", newline="") as arquivo:
        return {linha["CODIGO_INEP"].strip(): linha for linha in csv.DictReader(arquivo, delimiter=";")}


def tabela_escola(pacote: zipfile.ZipFile) -> str:
    nomes = [n for n in pacote.namelist() if re.search(r"Tabela_Escola_2025.*\.csv$", n)]
    if len(nomes) != 1:
        raise SystemExit("esperava uma Tabela_Escola de 2025 no zip, achei: {}".format(nomes))
    return nomes[0]


def conferir_md5(pacote: zipfile.ZipFile, nome: str) -> str:
    """Compara a tabela com o md5 publicado dentro do proprio zip."""
    arquivos_md5 = [n for n in pacote.namelist() if n.lower().endswith(".txt") and "md5" in n.lower()]
    if not arquivos_md5:
        return "sem arquivo de md5 no zip"
    texto = pacote.read(arquivos_md5[0]).decode("latin-1")
    base = Path(nome).name
    # O arquivo de md5 escreve "_v2" e o zip, "_V2", no nome das tabelas.
    linha = next((l for l in texto.splitlines() if base.lower() in l.lower()), None)
    if linha is None:
        return "tabela nao listada no arquivo de md5"
    achado = re.search(r"[0-9a-fA-F]{32}", linha)
    if achado is None:
        return "linha da tabela sem md5"
    esperado = achado.group(0).lower()
    resumo = hashlib.md5()
    with pacote.open(nome) as binario:
        for bloco in iter(lambda: binario.read(1 << 20), b""):
            resumo.update(bloco)
    if resumo.hexdigest() != esperado:
        raise SystemExit("md5 divergente em {}: {} != {}".format(base, resumo.hexdigest(), esperado))
    return "ok ({})".format(esperado)


def main():
    catalogo = ler_catalogo()
    pares = ler_pares()
    DESTINO.mkdir(parents=True, exist_ok=True)

    resumo = defaultdict(Counter)
    invalidas = []
    uf_recuperadas = []
    vistos = set()
    saida = DESTINO / "escolas_censo_2025_coordenadas.csv"
    with zipfile.ZipFile(ZIP_CENSO) as pacote, open(saida, "w", encoding="utf-8", newline="") as arquivo:
        nome = tabela_escola(pacote)
        print("md5 da tabela:", conferir_md5(pacote, nome))
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(COLUNAS_CENSO + ["COORDENADA_CATALOGO", "LATITUDE_INEP", "LONGITUDE_INEP",
                                           "NIVEL_PAR_CNEFE", "LATITUDE_CNEFE", "LONGITUDE_CNEFE"])
        with pacote.open(nome) as binario:
            leitor = csv.DictReader(io.TextIOWrapper(binario, encoding="latin-1", newline=""), delimiter=";")
            for linha in leitor:
                codigo = (linha["CO_ENTIDADE"] or "").strip()
                uf = (linha["SG_UF"] or "").strip()
                if not uf:
                    uf = UF_POR_CODIGO.get((linha["CO_MUNICIPIO"] or "")[:2], "")
                    linha["SG_UF"] = uf
                    uf_recuperadas.append(linha)
                if not codigo or not uf:
                    invalidas.append(linha)
                    continue
                if codigo in vistos:
                    raise SystemExit("codigo INEP repetido no Censo 2025: {}".format(codigo))
                vistos.add(codigo)

                item = catalogo.get(codigo)
                lat = (item["Latitude"] or "").strip() if item else ""
                lon = (item["Longitude"] or "").strip() if item else ""
                if item is None:
                    categoria = "FORA_DO_CATALOGO"
                elif lat and lon:
                    categoria = "COM_COORDENADA"
                else:
                    categoria = "SEM_COORDENADA"

                par = pares.get(codigo) or {}
                escritor.writerow([linha[c] for c in COLUNAS_CENSO] + [
                    categoria, lat, lon, par.get("NIVEL", ""), par.get("LAT_CNEFE", ""), par.get("LON_CNEFE", "")])

                for grupo in (uf, "BR"):
                    contagem = resumo[grupo]
                    contagem["ESCOLAS_2025"] += 1
                    contagem[categoria] += 1
                    if categoria != "COM_COORDENADA":
                        contagem["SEM_COORD_SITUACAO_" + linha["TP_SITUACAO_FUNCIONAMENTO"]] += 1
                        if par:
                            contagem["SEM_COORD_COM_PAR_CNEFE"] += 1

    colunas = ["UF", "ESCOLAS_2025"] + CATEGORIAS + ["PCT_SEM_COORDENADA_INEP", "SEM_COORD_COM_PAR_CNEFE",
                                                     "SEM_COORD_SITUACAO_1", "SEM_COORD_SITUACAO_2",
                                                     "SEM_COORD_SITUACAO_3"]
    with open(DESTINO / "resumo_por_uf.csv", "w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(colunas)
        for uf in sorted(k for k in resumo if k != "BR") + ["BR"]:
            c = resumo[uf]
            sem = c["SEM_COORDENADA"] + c["FORA_DO_CATALOGO"]
            escritor.writerow([uf, c["ESCOLAS_2025"]] + [c[k] for k in CATEGORIAS] +
                              ["{:.1f}".format(100 * sem / c["ESCOLAS_2025"])] +
                              [c[k] for k in colunas[6:]])

    br = resumo["BR"]
    print("ufs:", len(resumo) - 1)
    print("UF recuperada pelo codigo do municipio:", [(l["CO_ENTIDADE"], l["SG_UF"]) for l in uf_recuperadas])
    print("linhas descartadas (sem codigo ou sem UF):", len(invalidas))
    for linha in invalidas:
        print("  ", {k: linha[k] for k in COLUNAS_CENSO}, "colunas preenchidas:",
              sum(1 for v in linha.values() if v))
    print(dict(br))
    print("gravado em", DESTINO.relative_to(RAIZ))


if __name__ == "__main__":
    main()
