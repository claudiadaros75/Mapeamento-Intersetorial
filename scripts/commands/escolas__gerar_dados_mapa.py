#!/usr/bin/env python3
"""Gera os arquivos JSON compactos do mapa web de escolas INEP x CNEFE, um por UF.

Entradas: o catalogo do INEP, o recorte de escolas do CNEFE e as saidas de
escolas__parear_inep_cnefe.py (pares.csv, ambiguos.csv, resumo_*.csv).

Saidas em web/data/escolas/:
    <UF>.json   {"uf", "inep": [...], "cnefe": [...]} - linhas em arrays (sem
                nomes de campo repetidos) para caber no navegador:
        inep : [codigo, nome, lat, lon, status, restricao, idx_cnefe, distancia_m, endereco, municipio]
               status = N1..N4 | AMB (ambigua) | SEM (sem par)
               restricao = F (funcionando) | P (paralisada) | E (exclusiva/especial)
               idx_cnefe = posicao do par na lista "cnefe" (-1 sem par)
        cnefe: [cod_unico_endereco, nome, lat, lon, idx_inep, endereco]
    index.json  resumo por UF e distancias (alimenta o painel do mapa)

Uso:
    .venv/bin/python scripts/commands/escolas__gerar_dados_mapa.py
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import escolas__parear_inep_cnefe as par  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent.parent
DIR_PAREAMENTO = RAIZ / "data" / "escolas_pareamento"
DIR_WEB = RAIZ / "web" / "data" / "escolas"


def coord(texto):
    """Coordenada arredondada a 6 casas (~0,1 m) ou None."""
    valor = par.para_float(texto)
    return round(valor, 6) if valor is not None else None


def restricao_curta(texto: str) -> str:
    """Resume a coluna Restricao de Atendimento em F/P/E."""
    if texto.startswith("ESCOLA EM FUNCIONAMENTO"):
        return "F"
    if texto == "ESCOLA PARALISADA":
        return "P"
    return "E"


def ler_csv(caminho: Path) -> list:
    """Le um CSV ';' do pareamento."""
    with open(caminho, encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=";"))


def principal() -> None:
    """Monta e grava um JSON por UF mais o index.json."""
    pares = defaultdict(dict)  # uf -> codigo_inep -> linha do par
    for linha in ler_csv(DIR_PAREAMENTO / "pares.csv"):
        pares[linha["UF"]][linha["CODIGO_INEP"]] = linha
    ambiguos = {(l["UF"], l["CODIGO_INEP"]) for l in ler_csv(DIR_PAREAMENTO / "ambiguos.csv")}
    resumo = ler_csv(DIR_PAREAMENTO / "resumo_por_uf.csv")
    distancias = ler_csv(DIR_PAREAMENTO / "resumo_distancias.csv")
    ufs = [l["UF"] for l in resumo if l["UF"] != "BR"]

    catalogo = defaultdict(list)
    with open(par.CATALOGO, encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            if linha["UF"] in ufs:
                catalogo[linha["UF"]].append(linha)

    DIR_WEB.mkdir(parents=True, exist_ok=True)
    disponiveis = par.ufs_com_cnefe()
    total_bytes = 0
    for uf in ufs:
        cnefe_linhas = []
        posicao_cnefe = {}
        for registro in par.carregar_cnefe(disponiveis[uf]):
            posicao_cnefe[registro["id"]] = len(cnefe_linhas)
            cnefe_linhas.append([
                registro["id"], registro["nome"],
                round(registro["lat"], 6) if registro["lat"] is not None else None,
                round(registro["lon"], 6) if registro["lon"] is not None else None,
                -1, registro["endereco"],
            ])

        inep_linhas = []
        for linha in catalogo[uf]:
            codigo = linha["Código INEP"]
            p = pares[uf].get(codigo)
            if p:
                status, idx = p["NIVEL"], posicao_cnefe[p["COD_UNICO_ENDERECO_CNEFE"]]
                dist = round(float(p["DISTANCIA_M"])) if p["DISTANCIA_M"] else None
                cnefe_linhas[idx][4] = len(inep_linhas)
            else:
                status, idx, dist = ("AMB" if (uf, codigo) in ambiguos else "SEM"), -1, None
            inep_linhas.append([
                codigo, linha["Escola"], coord(linha["Latitude"]), coord(linha["Longitude"]),
                status, restricao_curta(linha["Restrição de Atendimento"]), idx, dist,
                linha["Endereço"], linha["Município"],
            ])

        destino = DIR_WEB / "{}.json".format(uf)
        with open(destino, "w", encoding="utf-8") as arquivo:
            json.dump({"uf": uf, "inep": inep_linhas, "cnefe": cnefe_linhas}, arquivo,
                      ensure_ascii=False, separators=(",", ":"))
        tamanho = destino.stat().st_size
        total_bytes += tamanho
        print("{}: {} INEP, {} CNEFE -> {} ({:.1f} MB)".format(
            uf, len(inep_linhas), len(cnefe_linhas), destino.name, tamanho / 1e6))

    with open(DIR_WEB / "index.json", "w", encoding="utf-8") as arquivo:
        json.dump({"resumo": resumo, "distancias": distancias}, arquivo, ensure_ascii=False, indent=1)
    print("total: {:.1f} MB em {}".format(total_bytes / 1e6, DIR_WEB))


if __name__ == "__main__":
    principal()
