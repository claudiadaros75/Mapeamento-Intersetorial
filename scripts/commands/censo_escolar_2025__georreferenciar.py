#!/usr/bin/env python3
"""Georreferencia as escolas do Censo Escolar 2025, em cascata.

Rode antes censo_escolar_2025__cruzar_catalogo.py e escolas__parear_inep_cnefe.py.

Ordem de localizacao de cada escola:
    1. coordenada do Catalogo de Escolas do INEP;
    2. escola do catalogo sem coordenada: o par que ela ja tem no CNEFE;
    3. escola fora do catalogo: regras N1-N4 de escolas__parear_inep_cnefe.py,
       so com registros do CNEFE ainda livres, para manter o pareamento 1:1;
    4. sem localizacao: vai para a tabela e o CSV de escolas nao localizadas.

As escolas fora do catalogo nao tem endereco em 2025, entao N1 e N2 so se aplicam
quando ha endereco nos microdados de 2024 ou 2023. N3 e N4 usam nome e municipio.

Saidas:
    data/censo_escolar_2025/escolas_censo_2025_georreferenciadas.csv  todas as escolas
    data/censo_escolar_2025/pares_novos_fora_do_catalogo.csv          auditoria da etapa 3
    web/data/censo_2025/escolas.json                                  dados do mapa
    web/data/censo_2025/escolas_sem_localizacao.csv                   escolas nao localizadas

Uso:
    .venv/bin/python scripts/commands/censo_escolar_2025__georreferenciar.py
"""

import csv
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import escolas__parear_inep_cnefe as par  # noqa: E402
import escolas_normalizacao as nz  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent.parent
DIR_DADOS = RAIZ / "data" / "censo_escolar_2025"
ENTRADA = DIR_DADOS / "escolas_censo_2025_coordenadas.csv"
DIR_ZIPS = RAIZ / "data" / "inep_censo_escolar" / "zipfiles"
DIR_WEB = RAIZ / "web" / "data" / "censo_2025"
PARES = par.DIR_SAIDA / "pares.csv"
AMBIGUOS = par.DIR_SAIDA / "ambiguos.csv"
CNEFE_LIVRE = par.DIR_SAIDA / "cnefe_sem_par.csv"

CASAS = 5  # cerca de 1 m
SITUACAO = {"1": "Em atividade", "2": "Paralisada", "3": "Extinta"}
REDE = {"1": "Federal", "2": "Estadual", "3": "Municipal", "4": "Privada"}
LOCAL = {"1": "Urbana", "2": "Rural"}


def ler_csv(caminho: Path, delimitador: str = ";", codificacao: str = "utf-8") -> list:
    with open(caminho, encoding=codificacao, newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=delimitador))


def enderecos_anteriores(codigos: set) -> dict:
    """Endereco mais recente das escolas pedidas nos microdados de 2024 e 2023."""
    achados = {}
    for ano in (2024, 2023):
        with zipfile.ZipFile(DIR_ZIPS / "microdados_censo_escolar_{}.zip".format(ano)) as pacote:
            nome = next(n for n in pacote.namelist() if re.search(r"microdados_ed_basica_\d+\.csv$", n))
            with pacote.open(nome) as binario:
                texto = io.TextIOWrapper(binario, encoding="latin-1", newline="")
                for linha in csv.DictReader(texto, delimiter=";"):
                    codigo = linha["CO_ENTIDADE"]
                    if codigo in codigos and codigo not in achados and (linha.get("DS_ENDERECO") or "").strip():
                        achados[codigo] = {"ano": ano, "logradouro": linha["DS_ENDERECO"],
                                           "numero": linha.get("NU_ENDERECO", ""), "cep": linha.get("CO_CEP", "")}
    return achados


def parear_fora_do_catalogo(fora: list) -> tuple:
    """Roda N1-N4 nas escolas fora do catalogo. Devolve ({codigo: par}, {codigo: nivel ambiguo}, auditoria)."""
    enderecos = enderecos_anteriores({e["CO_ENTIDADE"] for e in fora})
    print("escolas fora do catalogo com endereco em censo anterior:", len(enderecos))

    livres_por_uf = defaultdict(set)
    for linha in ler_csv(CNEFE_LIVRE):
        livres_por_uf[linha["UF"]].add(linha["COD_UNICO_ENDERECO_CNEFE"])

    por_uf = defaultdict(list)
    for linha in fora:
        codigo = linha["CO_ENTIDADE"]
        endereco = enderecos.get(codigo, {})
        por_uf[linha["SG_UF"]].append({
            "id": codigo,
            "nome": linha["NO_ENTIDADE"],
            "municipio": linha["CO_MUNICIPIO"],
            "cep": nz.normalizar_cep(endereco.get("cep", "")),
            "numero": nz.normalizar_numero(endereco.get("numero", "")),
            "logradouro": nz.normalizar_logradouro(endereco["logradouro"]) if endereco else "",
            "nome_exato": nz.nome_escola_exato(linha["NO_ENTIDADE"]),
            "nucleo": nz.nome_escola_nucleo(linha["NO_ENTIDADE"]),
        })

    arquivos = par.ufs_com_cnefe()
    pares, ambiguos, auditoria = {}, {}, []
    for uf, escolas in sorted(por_uf.items()):
        cnefe = [r for r in par.carregar_cnefe(arquivos[uf]) if r["id"] in livres_por_uf[uf]]
        achados, ambiguos_uf, _, _ = par.parear_uf(escolas, cnefe)
        for nivel, escola, registro, nota, n_cand in achados:
            pares[escola["id"]] = {"NIVEL": nivel, "LAT_CNEFE": registro["lat"], "LON_CNEFE": registro["lon"],
                                   "NOME_CNEFE": registro["nome"]}
            auditoria.append({"NIVEL": nivel, "UF": uf, "CO_MUNICIPIO": escola["municipio"], "CO_ENTIDADE": escola["id"],
                              "NO_ENTIDADE": escola["nome"], "NOME_CNEFE": registro["nome"],
                              "ENDERECO_CNEFE": registro["endereco"], "COD_UNICO_ENDERECO": registro["id"],
                              "NOTA_NOME": round(nota, 1), "N_CANDIDATOS": n_cand,
                              "ANO_ENDERECO_INEP": enderecos.get(escola["id"], {}).get("ano", ""),
                              "LAT_CNEFE": registro["lat"], "LON_CNEFE": registro["lon"]})
        for codigo, (nivel, _, _) in ambiguos_uf.items():
            ambiguos[codigo] = nivel
    return pares, ambiguos, auditoria


def escrever(caminho: Path, colunas: list, linhas: list, codificacao: str = "utf-8") -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding=codificacao, newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas, delimiter=";")
        escritor.writeheader()
        escritor.writerows(linhas)


def main():
    escolas = ler_csv(ENTRADA)
    pares_catalogo = {l["CODIGO_INEP"]: l for l in ler_csv(PARES)}
    ambiguos_catalogo = {l["CODIGO_INEP"]: l["NIVEL_AMBIGUIDADE"] for l in ler_csv(AMBIGUOS)}
    with open(par.CATALOGO, encoding="utf-8-sig", newline="") as arquivo:
        catalogo = {l["Código INEP"].strip(): l for l in csv.DictReader(arquivo)}

    fora = [e for e in escolas if e["COORDENADA_CATALOGO"] == "FORA_DO_CATALOGO"]
    pares_novos, ambiguos_novos, auditoria = parear_fora_do_catalogo(fora)

    todas, sem_localizacao, linhas_mapa = [], [], []
    contagem = Counter()
    fora_do_brasil = 0
    for e in escolas:
        codigo = e["CO_ENTIDADE"]
        no_catalogo = codigo in catalogo
        municipio = e["NO_MUNICIPIO"] or (catalogo[codigo]["Município"] if no_catalogo else "")
        lat = lon = nivel = nome_cnefe = ""
        if e["COORDENADA_CATALOGO"] == "COM_COORDENADA":
            origem, lat, lon = "CATALOGO_INEP", e["LATITUDE_INEP"], e["LONGITUDE_INEP"]
        elif codigo in pares_catalogo:
            p = pares_catalogo[codigo]
            origem, lat, lon, nivel, nome_cnefe = "CNEFE", p["LAT_CNEFE"], p["LON_CNEFE"], p["NIVEL"], p["NOME_CNEFE"]
        elif codigo in pares_novos:
            p = pares_novos[codigo]
            origem, lat, lon, nivel, nome_cnefe = "CNEFE", p["LAT_CNEFE"], p["LON_CNEFE"], p["NIVEL"], p["NOME_CNEFE"]
        else:
            origem = "SEM_LOCALIZACAO"

        contagem[origem + ("_" + nivel if nivel else "")] += 1
        linha = {"CO_ENTIDADE": codigo, "NO_ENTIDADE": e["NO_ENTIDADE"], "SG_UF": e["SG_UF"],
                 "CO_MUNICIPIO": e["CO_MUNICIPIO"], "NO_MUNICIPIO": municipio,
                 "REDE": REDE.get(e["TP_DEPENDENCIA"], ""), "LOCALIZACAO": LOCAL.get(e["TP_LOCALIZACAO"], ""),
                 "SITUACAO_2025": SITUACAO.get(e["TP_SITUACAO_FUNCIONAMENTO"], ""),
                 "ORIGEM_LOCALIZACAO": origem, "NIVEL_CNEFE": nivel, "NOME_CNEFE": nome_cnefe,
                 "LATITUDE": lat, "LONGITUDE": lon}
        todas.append(linha)

        if origem == "SEM_LOCALIZACAO":
            ambiguo = ambiguos_catalogo.get(codigo) or ambiguos_novos.get(codigo)
            if ambiguo:
                motivo = "Empate entre registros do CNEFE ({})".format(ambiguo)
            elif no_catalogo:
                motivo = "No catálogo sem coordenada e sem par no CNEFE"
            else:
                motivo = "Fora do catálogo e sem par no CNEFE"
            sem_localizacao.append({k: linha[k] for k in ("CO_ENTIDADE", "NO_ENTIDADE", "SG_UF", "CO_MUNICIPIO",
                                                          "NO_MUNICIPIO", "REDE", "LOCALIZACAO", "SITUACAO_2025")} | {
                "ENDERECO_CATALOGO": catalogo[codigo]["Endereço"] if no_catalogo else "", "MOTIVO": motivo})
            contagem["MOTIVO: " + motivo.split(" (")[0]] += 1

        la = round(float(lat), CASAS) if lat != "" else None
        lo = round(float(lon), CASAS) if lon != "" else None
        if la is not None and lo is not None and not (-34 <= la <= 6 and -75 <= lo <= -28):
            fora_do_brasil += 1
        linhas_mapa.append([codigo, e["NO_ENTIDADE"], e["SG_UF"], municipio, int(e["TP_SITUACAO_FUNCIONAMENTO"]),
                            int(e["TP_DEPENDENCIA"]), int(e["TP_LOCALIZACAO"]),
                            "I" if origem == "CATALOGO_INEP" else (nivel or "S"), la, lo])

    assert len(todas) == len(escolas) == len(linhas_mapa)
    assert sum(v for k, v in contagem.items() if k.startswith(("CATALOGO", "CNEFE", "SEM_LOC"))) == len(escolas)

    escrever(DIR_DADOS / "escolas_censo_2025_georreferenciadas.csv", list(todas[0]), todas)
    if auditoria:
        escrever(DIR_DADOS / "pares_novos_fora_do_catalogo.csv", list(auditoria[0]), auditoria)
    # utf-8-sig: o Excel so reconhece os acentos do CSV com BOM
    escrever(DIR_WEB / "escolas_sem_localizacao.csv", list(sem_localizacao[0]), sem_localizacao, "utf-8-sig")
    DIR_WEB.mkdir(parents=True, exist_ok=True)
    (DIR_WEB / "escolas.json").write_text(
        json.dumps({"colunas": ["codigo", "nome", "uf", "municipio", "situacao", "rede", "localizacao", "origem", "lat", "lon"],
                    "linhas": linhas_mapa}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    for chave in sorted(contagem):
        print(chave, contagem[chave])
    print("pares novos:", len(pares_novos), Counter(p["NIVEL"] for p in pares_novos.values()))
    print("coordenadas fora da caixa do Brasil:", fora_do_brasil)
    print("sem localizacao:", len(sem_localizacao))
    print("escolas.json: {:.1f} MB".format((DIR_WEB / "escolas.json").stat().st_size / 1e6))


if __name__ == "__main__":
    main()
