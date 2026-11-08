#!/usr/bin/env python3
"""Pareia as escolas do Catalogo do INEP com os estabelecimentos de ensino do CNEFE (niveis N1-N4).

Entradas (geradas antes por outros scripts):
    data/inep_catalogo_escolas/catalogo-escolas-unificado.csv  (inep_catalogo_escolas__baixar_dados.py)
    data/ibge_cnefe/escolas/cnefe_escolas_<NN_UF>.csv          (ibge_cnefe__extrair_escolas.py)
    data/ibge_malha_municipal/geojsonfiles/BR_municipios_2024_minima.geojson (nome -> codigo IBGE)

Niveis, sempre dentro do mesmo municipio e em cascata (quem pareia num
nivel nao e testado nos seguintes; cada registro do CNEFE e usado uma vez):
    N1  CEP + numero + logradouro (logradouro com similaridade >= LIMIAR_LOGRADOURO)
    N2  CEP + logradouro (numero ignorado); candidato com nome especifico que
        contradiz o do INEP (nota < LIMIAR_NOME_N2) e rejeitado
    N3  nome exato (so normalizado: acento, pontuacao, caixa)
    N4  nome ajustado (abreviacoes expandidas, termos genericos removidos,
        similaridade >= LIMIAR_N4)

Desempate quando ha mais de um candidato num nivel: similaridade do nome
(nucleo). Se o 2o colocado ficar a menos de MARGEM_AMBIGUO pontos do 1o, a
escola fica "ambigua" naquele nivel e segue para o proximo. A distancia
entre as coordenadas NUNCA e usada para decidir um par - ela e o que este
trabalho quer medir (ver docs/features/mapa-escolas-inep-cnefe.org, T6).

Saidas em data/escolas_pareamento/:
    pares.csv                                    todos os pares (todos os niveis)
    auditoria_N1_cep_numero_logradouro.csv ... auditoria_N4_nome_ajustado.csv
    ambiguos.csv, inep_sem_par.csv, cnefe_sem_par.csv
    resumo_por_uf.csv, resumo_distancias.csv

Uso:
    .venv/bin/python scripts/commands/escolas__parear_inep_cnefe.py          # UFs com CNEFE extraido
    .venv/bin/python scripts/commands/escolas__parear_inep_cnefe.py rr sp
"""

import argparse
import csv
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from rapidfuzz import fuzz, process

sys.path.insert(0, str(Path(__file__).resolve().parent))
import escolas_normalizacao as nz  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent.parent
CATALOGO = RAIZ / "data" / "inep_catalogo_escolas" / "catalogo-escolas-unificado.csv"
DIR_CNEFE = RAIZ / "data" / "ibge_cnefe" / "escolas"
MUNICIPIOS = RAIZ / "data" / "ibge_malha_municipal" / "geojsonfiles" / "BR_municipios_2024_minima.geojson"
DIR_SAIDA = RAIZ / "data" / "escolas_pareamento"

# Limiares em pontos de 0 a 100 (rapidfuzz). Valores iniciais da decisao D3;
# calibrar na validacao amostral (T11).
LIMIAR_LOGRADOURO = 85
LIMIAR_N4 = 85
MARGEM_AMBIGUO = 5
LIMIAR_MUNICIPIO = 90
# v3: no N2 (sem numero) um nome especifico do CNEFE que contradiz o do INEP
# derruba o candidato. Calibrado na amostra manual de 2026-11-07 (6/25 erros,
# todos com nota < 50) e conferido no agregado: N2 com nota < 50 tinha
# mediana de 120 m e 20% acima de 1 km, contra 22-32 m nos demais grupos.
LIMIAR_NOME_N2 = 50

NIVEIS = {
    "N1": "auditoria_N1_cep_numero_logradouro.csv",
    "N2": "auditoria_N2_cep_logradouro.csv",
    "N3": "auditoria_N3_nome_exato.csv",
    "N4": "auditoria_N4_nome_ajustado.csv",
}

COLUNAS_PAR = [
    "NIVEL", "UF", "CO_MUNICIPIO", "MUNICIPIO",
    "CODIGO_INEP", "NOME_INEP", "ENDERECO_INEP", "RESTRICAO_ATENDIMENTO", "LOCALIZACAO",
    "COD_UNICO_ENDERECO_CNEFE", "NOME_CNEFE", "ENDERECO_CNEFE",
    "CEP_INEP", "CEP_CNEFE", "CEP_GENERICO", "NUM_INEP", "NUM_CNEFE",
    "LOGRADOURO_INEP_NORM", "LOGRADOURO_CNEFE_NORM", "NOTA_LOGRADOURO",
    "NOME_INEP_CHAVE", "NOME_CNEFE_CHAVE", "NOTA_NOME", "N_CANDIDATOS",
    "LAT_INEP", "LON_INEP", "LAT_CNEFE", "LON_CNEFE", "NV_GEO_COORD_CNEFE",
    "DISTANCIA_M", "FAIXA_DISTANCIA", "SITUACAO_COORD",
]

# ------------------------------------------------------------------ carga


def carregar_municipios() -> dict:
    """{sigla_uf: {nome_normalizado: codigo_ibge}} a partir da malha municipal 2024."""
    with open(MUNICIPIOS, encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    por_uf = defaultdict(dict)
    for feicao in dados["features"]:
        p = feicao["properties"]
        por_uf[p["sigla_uf"]][nz.normalizar_texto(p["nome"])] = p["codarea"]
    return por_uf


def codigo_municipio(nome: str, uf: str, municipios: dict, cache: dict) -> tuple:
    """Codigo IBGE do municipio pelo nome; cai para similaridade dentro da UF. Devolve (codigo, metodo)."""
    chave = (uf, nome)
    if chave not in cache:
        tabela = municipios.get(uf, {})
        normalizado = nz.normalizar_texto(nome)
        if normalizado in tabela:
            cache[chave] = (tabela[normalizado], "exato")
        else:
            melhor = process.extractOne(normalizado, list(tabela), scorer=fuzz.ratio, score_cutoff=LIMIAR_MUNICIPIO)
            cache[chave] = (tabela[melhor[0]], "aproximado") if melhor else ("", "nao_encontrado")
    return cache[chave]


def para_float(texto: str):
    """Converte coordenada em float; None se vazia ou invalida."""
    try:
        valor = float((texto or "").strip())
        return valor if valor != 0 else None
    except ValueError:
        return None


def carregar_catalogo(ufs: set, municipios: dict) -> tuple:
    """Le o catalogo do INEP e devolve ({uf: [escola, ...]}, Counter de metodos de municipio, Counter de parse)."""
    por_uf = defaultdict(list)
    metodos, parse_ok, cache = Counter(), Counter(), {}
    with open(CATALOGO, encoding="utf-8-sig", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            uf = linha["UF"]
            if uf not in ufs:
                continue
            end = nz.parse_endereco_inep(linha["Endereço"])
            parse_ok["ok" if end["ok"] else "falhou"] += 1
            codigo, metodo = codigo_municipio(linha["Município"], uf, municipios, cache)
            metodos[metodo] += 1
            por_uf[uf].append({
                "id": linha["Código INEP"],
                "nome": linha["Escola"],
                "endereco": linha["Endereço"],
                "restricao": linha["Restrição de Atendimento"],
                "localizacao": linha["Localização"],
                "municipio_nome": linha["Município"],
                "municipio": codigo,
                "cep": end["cep"],
                "numero": end["numero"],
                "logradouro": nz.normalizar_logradouro(end["logradouro"]) if end["ok"] else "",
                "nome_exato": nz.nome_escola_exato(linha["Escola"]),
                "nucleo": nz.nome_escola_nucleo(linha["Escola"]),
                "lat": para_float(linha["Latitude"]),
                "lon": para_float(linha["Longitude"]),
            })
    return por_uf, metodos, parse_ok


def carregar_cnefe(caminho: Path) -> list:
    """Le o recorte de escolas do CNEFE de uma UF ja com as chaves normalizadas."""
    registros = []
    with open(caminho, encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo, delimiter=";"):
            nome = linha["DSC_ESTABELECIMENTO"]
            endereco = " ".join(p for p in (
                linha["NOM_TIPO_SEGLOGR"], linha["NOM_TITULO_SEGLOGR"], linha["NOM_SEGLOGR"] + ",",
                linha["NUM_ENDERECO"] if linha["NUM_ENDERECO"] != "0" else linha["DSC_MODIFICADOR"] or "S/N",
                linha["DSC_LOCALIDADE"] + ".", linha["CEP"],
            ) if p)
            registros.append({
                "id": linha["COD_UNICO_ENDERECO"],
                "municipio": linha["COD_MUNICIPIO"],
                "cep": nz.normalizar_cep(linha["CEP"]),
                "numero": nz.normalizar_numero(linha["NUM_ENDERECO"]),
                "logradouro": nz.logradouro_cnefe(
                    linha["NOM_TIPO_SEGLOGR"], linha["NOM_TITULO_SEGLOGR"], linha["NOM_SEGLOGR"]),
                "nome": nome,
                "endereco": endereco,
                "nome_exato": nz.nome_escola_exato(nome),
                "nucleo": nz.nome_escola_nucleo(nome) if nome.strip() else "",
                "generico": nz.nome_escola_generico(nome),
                "lat": para_float(linha["LATITUDE"]),
                "lon": para_float(linha["LONGITUDE"]),
                "nv_geo": linha["NV_GEO_COORD"],
            })
    return registros

# ------------------------------------------------------------------ pareamento


def nota_nucleos(a: str, b: str) -> float:
    """Similaridade 0-100 entre dois nucleos de nome.

    token_sort_ratio, ou token_set_ratio quando o menor nome tem 2+ palavras
    (v2): "MARIA GUEDES" contido em "MARIA GUEDES LIMA" vale 100. Com 1
    palavra so o set_ratio seria arriscado ("JOSE" estaria contido em tudo).
    """
    if not a or not b:
        return 0.0
    nota = fuzz.token_sort_ratio(a, b)
    if min(len(a.split()), len(b.split())) >= 2:
        nota = max(nota, fuzz.token_set_ratio(a, b))
    return nota


def nota_nome(escola: dict, registro: dict) -> float:
    """Similaridade 0-100 entre os nucleos de nome (0 se o CNEFE nao tem nome)."""
    return nota_nucleos(escola["nucleo"], registro["nucleo"])


def nota_logradouro(escola: dict, registro: dict) -> float:
    """Similaridade 0-100 entre logradouros normalizados (0 se algum estiver vazio)."""
    if not escola["logradouro"] or not registro["logradouro"]:
        return 0.0
    return fuzz.token_sort_ratio(escola["logradouro"], registro["logradouro"])


def decidir(escola: dict, candidatos: list):
    """Escolhe entre candidatos por nota de nome. Devolve (registro, nota_nome, ambiguo, pontuados)."""
    pontuados = sorted(((nota_nome(escola, c), c) for c in candidatos), key=lambda par: -par[0])
    if len(pontuados) > 1 and pontuados[0][0] - pontuados[1][0] < MARGEM_AMBIGUO:
        return None, pontuados[0][0], True, pontuados
    return pontuados[0][1], pontuados[0][0], False, pontuados


def candidatos_por_nivel(nivel: str, escola: dict, indices: dict, livres: set, nucleos_mun: dict) -> list:
    """Lista os registros do CNEFE ainda livres que satisfazem a chave do nivel para esta escola."""
    mun = escola["municipio"]
    if not mun:
        return []
    if nivel == "N1":
        if not (escola["cep"] and escola["numero"] and escola["logradouro"]):
            return []
        brutos = indices["N1"].get((mun, escola["cep"], escola["numero"]), [])
        return [c for c in brutos if c["id"] in livres and nota_logradouro(escola, c) >= LIMIAR_LOGRADOURO]
    if nivel == "N2":
        if not (escola["cep"] and escola["logradouro"]):
            return []
        brutos = indices["N2"].get((mun, escola["cep"]), [])
        return [c for c in brutos if c["id"] in livres and nota_logradouro(escola, c) >= LIMIAR_LOGRADOURO
                and (c["generico"] or nota_nome(escola, c) >= LIMIAR_NOME_N2)]
    if nivel == "N3":
        brutos = indices["N3"].get((mun, escola["nome_exato"]), [])
        return [c for c in brutos if c["id"] in livres]
    # N4: nucleos do municipio com similaridade acima do limiar
    registros = [r for r in nucleos_mun.get(mun, []) if r["id"] in livres]
    if not registros:
        return []
    nucleos = [r["nucleo"] for r in registros]
    indices = {i for _, _, i in process.extract(
        escola["nucleo"], nucleos, scorer=fuzz.token_sort_ratio, score_cutoff=LIMIAR_N4, limit=None)}
    if len(escola["nucleo"].split()) >= 2:
        # pre-filtro rapido em C; nota_nucleos confere a regra das 2+ palavras
        indices |= {i for _, _, i in process.extract(
            escola["nucleo"], nucleos, scorer=fuzz.token_set_ratio, score_cutoff=LIMIAR_N4, limit=None)}
    return [registros[i] for i in sorted(indices) if nota_nucleos(escola["nucleo"], nucleos[i]) >= LIMIAR_N4]


def parear_uf(escolas: list, cnefe: list) -> tuple:
    """Roda N1->N4 numa UF. Devolve (pares, ambiguos, ids_inep_pareados, ids_cnefe_usados)."""
    indices = {"N1": defaultdict(list), "N2": defaultdict(list), "N3": defaultdict(list)}
    nucleos_mun = defaultdict(list)
    for r in cnefe:
        if r["cep"]:
            indices["N2"][(r["municipio"], r["cep"])].append(r)
            if r["numero"]:
                indices["N1"][(r["municipio"], r["cep"], r["numero"])].append(r)
        if r["nome_exato"]:
            indices["N3"][(r["municipio"], r["nome_exato"])].append(r)
        if r["nucleo"]:
            nucleos_mun[r["municipio"]].append(r)

    livres = {r["id"] for r in cnefe}
    pendentes = list(escolas)
    pares, ambiguos = [], {}

    for nivel in NIVEIS:
        propostas = []
        for escola in pendentes:
            candidatos = candidatos_por_nivel(nivel, escola, indices, livres, nucleos_mun)
            if not candidatos:
                continue
            registro, nota, ambiguo, pontuados = decidir(escola, candidatos)
            if ambiguo:
                # guarda a primeira ambiguidade; se parear depois, e removida
                ambiguos.setdefault(escola["id"], (nivel, escola, pontuados[:5]))
                continue
            propostas.append((nota, len(candidatos), escola, registro))

        # 1:1 - a proposta de maior nota fica com o registro; as outras seguem
        propostas.sort(key=lambda p: -p[0])
        pareados_agora = set()
        for nota, n_cand, escola, registro in propostas:
            if registro["id"] not in livres or escola["id"] in pareados_agora:
                continue
            livres.discard(registro["id"])
            pareados_agora.add(escola["id"])
            ambiguos.pop(escola["id"], None)
            pares.append((nivel, escola, registro, nota, n_cand))
        pendentes = [e for e in pendentes if e["id"] not in pareados_agora]

    ids_inep = {e["id"] for _, e, _, _, _ in pares}
    ids_cnefe = {r["id"] for r in cnefe} - livres
    return pares, ambiguos, ids_inep, ids_cnefe

# ------------------------------------------------------------------ saida


def linha_par(uf: str, nivel: str, e: dict, r: dict, nota: float, n_cand: int) -> dict:
    """Monta a linha de auditoria de um par, com as chaves que casaram e a distancia."""
    if e["lat"] is not None and r["lat"] is not None:
        dist = nz.haversine_m(e["lat"], e["lon"], r["lat"], r["lon"])
        dist_txt, faixa, situacao = "{:.1f}".format(dist), nz.faixa_distancia(dist), "ok"
    else:
        dist_txt, faixa = "", ""
        situacao = "SEM_COORD_INEP" if e["lat"] is None else "SEM_COORD_CNEFE"
    return {
        "NIVEL": nivel, "UF": uf, "CO_MUNICIPIO": e["municipio"], "MUNICIPIO": e["municipio_nome"],
        "CODIGO_INEP": e["id"], "NOME_INEP": e["nome"], "ENDERECO_INEP": e["endereco"],
        "RESTRICAO_ATENDIMENTO": e["restricao"], "LOCALIZACAO": e["localizacao"],
        "COD_UNICO_ENDERECO_CNEFE": r["id"], "NOME_CNEFE": r["nome"], "ENDERECO_CNEFE": r["endereco"],
        "CEP_INEP": e["cep"], "CEP_CNEFE": r["cep"], "CEP_GENERICO": "S" if nz.cep_generico(e["cep"]) else "N",
        "NUM_INEP": e["numero"], "NUM_CNEFE": r["numero"],
        "LOGRADOURO_INEP_NORM": e["logradouro"], "LOGRADOURO_CNEFE_NORM": r["logradouro"],
        "NOTA_LOGRADOURO": "{:.0f}".format(nota_logradouro(e, r)),
        "NOME_INEP_CHAVE": e["nome_exato"] if nivel == "N3" else e["nucleo"],
        "NOME_CNEFE_CHAVE": r["nome_exato"] if nivel == "N3" else r["nucleo"],
        "NOTA_NOME": "{:.0f}".format(nota), "N_CANDIDATOS": n_cand,
        "LAT_INEP": e["lat"] if e["lat"] is not None else "", "LON_INEP": e["lon"] if e["lon"] is not None else "",
        "LAT_CNEFE": r["lat"] if r["lat"] is not None else "", "LON_CNEFE": r["lon"] if r["lon"] is not None else "",
        "NV_GEO_COORD_CNEFE": r["nv_geo"], "DISTANCIA_M": dist_txt, "FAIXA_DISTANCIA": faixa,
        "SITUACAO_COORD": situacao,
    }


def percentil(valores: list, p: float) -> float:
    """Percentil por interpolacao linear (valores ja ordenados)."""
    if not valores:
        return float("nan")
    k = (len(valores) - 1) * p
    baixo = int(k)
    alto = min(baixo + 1, len(valores) - 1)
    return valores[baixo] + (valores[alto] - valores[baixo]) * (k - baixo)


def escrever_csv(caminho: Path, colunas: list, linhas: list) -> None:
    """Grava CSV UTF-8 com separador ';' (o mesmo do restante do projeto)."""
    with open(caminho, "w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas, delimiter=";")
        escritor.writeheader()
        escritor.writerows(linhas)


def ufs_com_cnefe() -> dict:
    """{sigla_uf: caminho} dos recortes de CNEFE ja extraidos."""
    return {c.stem.rsplit("_", 1)[-1]: c for c in sorted(DIR_CNEFE.glob("cnefe_escolas_*.csv"))}


def principal() -> None:
    """Le a linha de comando, pareia as UFs pedidas e grava pares, auditorias e resumos."""
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument("ufs", nargs="*", type=str.upper, help="siglas das UFs (padrao: todas com CNEFE extraido)")
    argumentos = analisador.parse_args()

    disponiveis = ufs_com_cnefe()
    ufs = argumentos.ufs or list(disponiveis)
    faltando = [uf for uf in ufs if uf not in disponiveis]
    if faltando:
        raise SystemExit("CNEFE nao extraido para {} - rode ibge_cnefe__extrair_escolas.py".format(faltando))

    inicio = time.time()
    municipios = carregar_municipios()
    catalogo, metodos_mun, parse = carregar_catalogo(set(ufs), municipios)
    print("catalogo: {} escolas em {} UF(s) | municipio: {} | endereco: {}".format(
        sum(len(v) for v in catalogo.values()), len(ufs), dict(metodos_mun), dict(parse)))

    DIR_SAIDA.mkdir(parents=True, exist_ok=True)
    todos_pares, linhas_ambiguos, linhas_inep_sem, linhas_cnefe_sem, resumo = [], [], [], [], []
    for uf in ufs:
        t = time.time()
        escolas = catalogo.get(uf, [])
        cnefe = carregar_cnefe(disponiveis[uf])
        pares, ambiguos, ids_inep, ids_cnefe = parear_uf(escolas, cnefe)
        linhas = [linha_par(uf, nv, e, r, nota, n) for nv, e, r, nota, n in pares]
        todos_pares.extend(linhas)

        for nivel, e, pontuados in ambiguos.values():
            linhas_ambiguos.append({
                "UF": uf, "NIVEL_AMBIGUIDADE": nivel, "CODIGO_INEP": e["id"], "NOME_INEP": e["nome"],
                "ENDERECO_INEP": e["endereco"], "N_CANDIDATOS": len(pontuados),
                "CANDIDATOS_CNEFE": " | ".join("{} [{}] nota={:.0f}".format(c["nome"] or "(sem nome)", c["id"], s)
                                              for s, c in pontuados),
            })
        for e in escolas:
            if e["id"] not in ids_inep and e["id"] not in ambiguos:
                linhas_inep_sem.append({
                    "UF": uf, "CODIGO_INEP": e["id"], "NOME_INEP": e["nome"], "ENDERECO_INEP": e["endereco"],
                    "CO_MUNICIPIO": e["municipio"], "RESTRICAO_ATENDIMENTO": e["restricao"],
                    "LAT_INEP": e["lat"] or "", "LON_INEP": e["lon"] or "",
                })
        for r in cnefe:
            if r["id"] not in ids_cnefe:
                linhas_cnefe_sem.append({
                    "UF": uf, "COD_UNICO_ENDERECO_CNEFE": r["id"], "NOME_CNEFE": r["nome"],
                    "ENDERECO_CNEFE": r["endereco"], "CO_MUNICIPIO": r["municipio"],
                    "LAT_CNEFE": r["lat"] or "", "LON_CNEFE": r["lon"] or "",
                })

        por_nivel = Counter(l["NIVEL"] for l in linhas)
        linha_resumo = {"UF": uf, "ESCOLAS_INEP": len(escolas), "ESTAB_CNEFE": len(cnefe)}
        for nivel in NIVEIS:
            linha_resumo[nivel] = por_nivel[nivel]
        linha_resumo.update({
            "PAREADAS": len(linhas), "PCT_PAREADAS": "{:.1f}".format(100 * len(linhas) / (len(escolas) or 1)),
            "AMBIGUAS": len(ambiguos), "INEP_SEM_PAR": len(escolas) - len(linhas) - len(ambiguos),
            "CNEFE_SEM_PAR": len(cnefe) - len(ids_cnefe),
            "PARES_SEM_COORD_INEP": sum(1 for l in linhas if l["SITUACAO_COORD"] == "SEM_COORD_INEP"),
        })
        resumo.append(linha_resumo)
        print("[{}] {:6d} INEP x {:6d} CNEFE | N1 {N1} N2 {N2} N3 {N3} N4 {N4} | pareadas {PCT_PAREADAS}% "
              "| ambiguas {AMBIGUAS} | sem par {INEP_SEM_PAR} | {t:.1f}s".format(
                  uf, len(escolas), len(cnefe), t=time.time() - t, **linha_resumo))

    # --- gravacao
    escrever_csv(DIR_SAIDA / "pares.csv", COLUNAS_PAR, todos_pares)
    for nivel, nome in NIVEIS.items():
        escrever_csv(DIR_SAIDA / nome, COLUNAS_PAR, [l for l in todos_pares if l["NIVEL"] == nivel])
    escrever_csv(DIR_SAIDA / "ambiguos.csv", ["UF", "NIVEL_AMBIGUIDADE", "CODIGO_INEP", "NOME_INEP",
                                              "ENDERECO_INEP", "N_CANDIDATOS", "CANDIDATOS_CNEFE"], linhas_ambiguos)
    escrever_csv(DIR_SAIDA / "inep_sem_par.csv", ["UF", "CODIGO_INEP", "NOME_INEP", "ENDERECO_INEP", "CO_MUNICIPIO",
                                                  "RESTRICAO_ATENDIMENTO", "LAT_INEP", "LON_INEP"], linhas_inep_sem)
    escrever_csv(DIR_SAIDA / "cnefe_sem_par.csv", ["UF", "COD_UNICO_ENDERECO_CNEFE", "NOME_CNEFE", "ENDERECO_CNEFE",
                                                   "CO_MUNICIPIO", "LAT_CNEFE", "LON_CNEFE"], linhas_cnefe_sem)
    total: dict = {"UF": "BR"}
    for chave in resumo[0] if resumo else []:
        if chave not in ("UF", "PCT_PAREADAS"):
            total[chave] = sum(int(l[chave]) for l in resumo)
    total["PCT_PAREADAS"] = "{:.1f}".format(100 * total.get("PAREADAS", 0) / (total.get("ESCOLAS_INEP", 0) or 1))
    escrever_csv(DIR_SAIDA / "resumo_por_uf.csv", list(total), resumo + [total])

    # distancias por nivel x UF (+ BR)
    grupos = defaultdict(list)
    for l in todos_pares:
        if l["DISTANCIA_M"]:
            d = float(l["DISTANCIA_M"])
            for chave in ((l["UF"], l["NIVEL"]), (l["UF"], "TODOS"), ("BR", l["NIVEL"]), ("BR", "TODOS")):
                grupos[chave].append(d)
    linhas_dist = []
    for (uf, nivel), valores in sorted(grupos.items()):
        valores.sort()
        faixas = Counter(nz.faixa_distancia(v) for v in valores)
        linhas_dist.append({
            "UF": uf, "NIVEL": nivel, "PARES_COM_DISTANCIA": len(valores),
            "MEDIANA_M": "{:.0f}".format(statistics.median(valores)), "P90_M": "{:.0f}".format(percentil(valores, 0.9)),
            "MAX_M": "{:.0f}".format(valores[-1]),
            **{"PCT_" + f.split("_", 1)[1]: "{:.1f}".format(100 * faixas[f] / len(valores))
               for f in ("a_<50m", "b_50-200m", "c_200m-1km", "d_1-5km", "e_>5km")},
        })
    if linhas_dist:
        escrever_csv(DIR_SAIDA / "resumo_distancias.csv", list(linhas_dist[0]), linhas_dist)

    print("\nBR: {ESCOLAS_INEP} INEP | N1 {N1} N2 {N2} N3 {N3} N4 {N4} | pareadas {PAREADAS} ({PCT_PAREADAS}%) | "
          "ambiguas {AMBIGUAS} | INEP sem par {INEP_SEM_PAR} | CNEFE sem par {CNEFE_SEM_PAR}".format(**total))
    for l in linhas_dist:
        if l["UF"] == "BR":
            print("  distancia {NIVEL:5s} n={PARES_COM_DISTANCIA:6d} mediana={MEDIANA_M}m p90={P90_M}m "
                  "<50m={PCT_<50m}% >5km={PCT_>5km}%".format(**l))
    print("saida: {} ({:.0f}s)".format(DIR_SAIDA, time.time() - inicio))


if __name__ == "__main__":
    principal()
