#!/usr/bin/env python3
"""ETL: georreferencia as escolas do Censo Escolar (INEP) e gera escolas_do_censo_2024_georeferenciadas_com_cnefe_2022.csv.

Le os dados ja baixados por inep_censo_escolar__baixar_dados.py,
ibge_cnefe__baixar_dados.py e ipea_geobr_escolas__baixar_dados.py (scripts
separados deste - o download nao faz nenhuma transformacao) e produz uma
linha por escola do Censo Escolar, com LATITUDE/LONGITUDE de uma de duas
fontes (o nome do arquivo de saida ficou o mesmo por compatibilidade):

    1. Catalogo de Escolas do INEP (cadastro de 2023, via geobr/Ipea),
       ligado pelo codigo da escola (code_school = CO_ENTIDADE): nao
       depende de casamento por nome ou endereco.
    2. CNEFE 2022 (IBGE), pelo casamento em niveis descrito abaixo.

Qual das duas vale depende do nivel do casamento com o CNEFE
(NIVEL_CASAMENTO; decisao de 02/11/2026, ver
docs/09-revisao-coordenadas-inep-x-cnefe.org):

    niveis 1 e 2 (endereco)  - ponto do CNEFE: o endereco garante que e a
                               mesma escola, e o CNEFE marca o predio.
                               Excecao: nivel 2 com CEP generico segue a
                               regra dos niveis 3 e 4 (no Norte, escolas
                               diferentes dividem o CEP-base e o numero).
    niveis 3 e 4 (nome)      - ponto do INEP: o casamento por nome e menos
                               seguro (nas divergencias > 10 km, o INEP
                               estava certo em 84-90%, ver doc 08). CNEFE se
                               a escola nao tem ponto no INEP.
    sem casamento            - ponto do INEP, quando houver.

Status final (STATUS_GEOLOCALIZACAO):

    endereco_exato, cep_numero
                     - ponto do CNEFE (niveis 1 e 2; cep_numero tambem
                       quando o CEP e generico e a escola nao tem ponto
                       no INEP).
    inep_confirmado  - ponto do INEP; o CNEFE tem ponto a ate 300 m.
    inep_proximo     - ponto do INEP; o do CNEFE esta entre 300 m e 1 km.
    inep_divergente  - ponto do INEP; o do CNEFE esta a mais de 1 km (na
                       maioria, o casamento com o CNEFE pegou outra escola).
    inep_sem_cnefe   - ponto do INEP; o casamento nao achou ponto no CNEFE.
    nome_exato, nome_ajustado
                     - ponto do CNEFE, para quem nao tem coordenada no INEP
                       (ou tem um ponto do INEP repetido, ver abaixo).
    sem_correspondencia - nenhuma das duas fontes tem ponto.

Ponto do INEP repetido: quando 5 ou mais escolas do cadastro do INEP tem
exatamente o mesmo ponto (marcacao generica, como a sede da secretaria) e
o CNEFE tem ponto para a escola (niveis 3 e 4), usa-se o do CNEFE; o alerta
ponto_inep_repetido marca os dois casos.

O resultado do casamento com o CNEFE fica sempre em STATUS_CNEFE, com o
ponto em CNEFE_LATITUDE/CNEFE_LONGITUDE, mesmo quando a coordenada final
e a do INEP.

Estrategia de casamento com o CNEFE em niveis (decisoes e numeros em
docs/08-mapeamento-intersetorial-nacional-diagnostico-norte.org e
docs/09-revisao-coordenadas-inep-x-cnefe.org). A regra geral e
conservadora: escola sem coordenada e melhor que escola no lugar errado.

    nivel 1 - endereco_exato: CO_MUNICIPIO+CO_CEP+NU_ENDERECO (INEP) bate
             exato com COD_MUNICIPIO+CEP+NUM_ENDERECO (CNEFE) e o nome da
             rua tambem (palavras_logradouro: mesmo conjunto de palavras,
             abreviacoes expandidas; o tipo - RUA, AVENIDA... - so pesa
             quando as duas bases o informam).
    nivel 2 - cep_numero: o mesmo endereco, mas com a rua diferente ou
             ausente. O nome da escola nao precisa bater em nenhum dos
             dois. Numero "0" conta como sem numero (no CNEFE "0" e
             "S/N"). Varios pontos no mesmo endereco: escolhe o de nome
             mais parecido (a posicao e a mesma de qualquer forma). Varias
             escolas do INEP no mesmo endereco podem dividir o ponto (mesmo
             predio).
    nivel 3 - nome_exato: para quem os niveis 1 e 2 nao resolveram, o nome
             e igual nas duas bases no mesmo municipio, depois de tirar so
             acento, pontuacao e diferenca de maiusculas (normalizar_nome),
             e e unico dos dois lados - um so ponto no CNEFE e uma so
             escola no INEP com aquele nome naquele municipio.
    nivel 4 - nome_ajustado: a mesma regra do nivel 3, comparando o "nucleo"
             do nome (nucleo_nome: abreviacoes expandidas e palavras
             genericas como ESCOLA/MUNICIPAL/EMEF removidas).
             Nos niveis 3 e 4 um ponto ja usado em nivel anterior nao e
             reaproveitado.
    sem_correspondencia - nenhum nivel resolveu; o motivo (do nivel 4, o
             ultimo) fica em MOTIVO_GEOLOCALIZACAO.

Alertas (ALERTAS_GEOLOCALIZACAO, separados por "|") nao tiram a coordenada,
so marcam o que merece conferencia:

    cep_generico         - nivel 1 ou 2 com CEP terminado em "000" (CEP-base
                           do municipio): mesmo numero em ruas diferentes
                           pode coincidir.
    varios_no_endereco   - nivel 1 ou 2 com mais de um ponto do CNEFE no
                           mesmo endereco.
    ponto_compartilhado  - o mesmo ponto do CNEFE foi dado a mais de uma
                           escola do INEP.
    ponto_inep_repetido  - o ponto do INEP e o mesmo de 5 ou mais escolas do
                           cadastro do INEP.

Saidas:
    data/escolas_do_censo_2024_georeferenciadas_com_cnefe_2022.csv
        todas as colunas do INEP + as colunas de geolocalizacao.
    data/auditoria/escolas_inep_x_cnefe_2024.csv
        uma linha por escola do INEP com o ponto do CNEFE escolhido lado a
        lado (ids, nomes, nucleos, enderecos, estagio, motivo, alertas), o
        ponto do INEP e a distancia entre os dois - e o arquivo para
        auditar o casamento e a escolha da coordenada.
    data/auditoria/cnefe_ensino_nao_usados_2024.csv
        pontos de ensino do CNEFE que nenhuma escola usou.
    data/inep_catalogo_escolas_2023_marcado.csv
        copia do Catalogo de Escolas do INEP (so as UFs processadas, com a
        coordenada do INEP em INEP_LATITUDE/INEP_LONGITUDE), mais o nivel
        do casamento de cada escola, o ponto do CNEFE ligado, a distancia
        entre os dois pontos e a fonte da coordenada escolhida.
    data/cnefe_2022_ensino_marcado.csv
        copia dos pontos de ensino do CNEFE (todas as colunas originais),
        mais as escolas do INEP ligadas a cada ponto, o nivel e a
        distancia - separados por "|" quando o ponto serve a mais de uma
        escola (mesmo predio).

Cada saida e mesclada por UF: rodar so "am pa" substitui as linhas de AM e
PA e mantem as das outras UFs que ja estavam no arquivo.

Escolas sem coordenada continuam no CSV de saida (o Censo Escolar do INEP
e a lista mestra - nunca perdemos uma escola por falta de coordenada).
Estabelecimentos do CNEFE sem escola correspondente nao viram linha nova
no CSV principal - o CNEFE so empresta coordenada, nunca declara a
existencia de uma escola - mas ficam registrados no CSV de nao usados.

So o Censo Escolar de 2024 tem endereco completo (2025 removeu esses
campos - ver docs/05-plano-marcadores-escolas-inep.org), entao por
enquanto o cruzamento so funciona com o ano de 2024.

Uso:
    .venv/bin/python scripts/commands/escolas_dados__cruzar_inep_cnefe.py
    .venv/bin/python ... am pa
    .venv/bin/python ... --listar
"""

import argparse
import collections
import csv
import difflib
import math
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
DIR_INEP = RAIZ / "data" / "inep_censo_escolar" / "zipfiles"
DIR_CNEFE = RAIZ / "data" / "ibge_cnefe" / "zipfiles"
SAIDA_PADRAO = RAIZ / "data" / "escolas_do_censo_2024_georeferenciadas_com_cnefe_2022.csv"
SAIDA_INEP_MARCADO = RAIZ / "data" / "inep_catalogo_escolas_2023_marcado.csv"
SAIDA_CNEFE_MARCADO = RAIZ / "data" / "cnefe_2022_ensino_marcado.csv"
DIR_AUDITORIA = RAIZ / "data" / "auditoria"
ARQUIVO_INEP_COORDENADAS = RAIZ / "data" / "ipea_geobr_escolas" / "schools_2023.gpkg"

ANO_CENSO_ESCOLAR = "2024"

# sigla -> codigo IBGE da UF (mesmo mapeamento de ibge_cnefe__baixar_dados.py)
UFS = {
    "ro": "11", "ac": "12", "am": "13", "rr": "14", "pa": "15", "ap": "16",
    "to": "17", "ma": "21", "pi": "22", "ce": "23", "rn": "24", "pb": "25",
    "pe": "26", "al": "27", "se": "28", "ba": "29", "mg": "31", "es": "32",
    "rj": "33", "sp": "35", "pr": "41", "sc": "42", "rs": "43", "ms": "50",
    "mt": "51", "go": "52", "df": "53",
}
CODIGO_PARA_SIGLA = {codigo: sigla for sigla, codigo in UFS.items()}

STATUS_CNEFE = ["endereco_exato", "cep_numero", "nome_exato", "nome_ajustado", "sem_correspondencia"]
STATUS = [
    "endereco_exato", "cep_numero",
    "inep_confirmado", "inep_proximo", "inep_divergente", "inep_sem_cnefe",
    "nome_exato", "nome_ajustado", "sem_correspondencia",
]
# Nivel de cada casamento com o CNEFE (coluna NIVEL_CASAMENTO); sem casamento fica vazio
NIVEL_CASAMENTO = {"endereco_exato": 1, "cep_numero": 2, "nome_exato": 3, "nome_ajustado": 4}
# Niveis em que a coordenada escolhida e a do CNEFE (o endereco garante a escola)
NIVEIS_PONTO_CNEFE = {"endereco_exato", "cep_numero"}

# Concordancia entre o ponto do INEP e o do CNEFE (ver doc 08)
CONFIRMADO_ATE_KM = 0.3
DIVERGENTE_ACIMA_KM = 1.0
# A partir de quantas escolas no mesmo ponto o ponto do INEP e tratado como generico
PONTO_INEP_REPETIDO = 5

# Abreviacoes encontradas nos nomes reais do INEP e do CNEFE (AM, PA, SP),
# expandidas antes de comparar para que "ESC MUN" e "ESCOLA MUNICIPAL"
# virem a mesma coisa.
ABREVIACOES = {
    "ESC": "ESCOLA", "ESCOL": "ESCOLA",
    "MUN": "MUNICIPAL", "MUL": "MUNICIPAL", "MUNIC": "MUNICIPAL", "MUNICIP": "MUNICIPAL",
    "EST": "ESTADUAL", "ESTAD": "ESTADUAL",
    "ENS": "ENSINO", "FUND": "FUNDAMENTAL", "INF": "INFANTIL", "EDUC": "EDUCACIONAL",
    "PART": "PARTICULAR", "CONV": "CONVENIADA",
    "PROF": "PROFESSOR", "PROFA": "PROFESSORA",
    "DR": "DOUTOR", "DRA": "DOUTORA",
    "STO": "SANTO", "STA": "SANTA",
    "NSRA": "NOSSA SENHORA", "NSA": "NOSSA SENHORA", "NS": "NOSSA SENHORA", "SRA": "SENHORA",
    "PE": "PADRE", "CEL": "CORONEL", "GAL": "GENERAL", "GEN": "GENERAL", "MAL": "MARECHAL",
    "PRES": "PRESIDENTE", "GOV": "GOVERNADOR", "SEN": "SENADOR", "DEP": "DEPUTADO",
    "VER": "VEREADOR", "VEREAD": "VEREADOR",
}

# Tipos de logradouro (e suas abreviacoes nas duas bases). So contam como
# tipo na primeira palavra do endereco; em "ESTRADA", "EST" nao pode virar
# "ESTADUAL" como nos nomes de escola.
TIPOS_LOGRADOURO = {
    "R": "RUA", "RUA": "RUA",
    "AV": "AVENIDA", "AVN": "AVENIDA", "AVENIDA": "AVENIDA",
    "TV": "TRAVESSA", "TRAV": "TRAVESSA", "TRAVESSA": "TRAVESSA",
    "AL": "ALAMEDA", "ALAMEDA": "ALAMEDA",
    "EST": "ESTRADA", "ESTR": "ESTRADA", "ESTRADA": "ESTRADA",
    "ROD": "RODOVIA", "RODOVIA": "RODOVIA",
    "PC": "PRACA", "PCA": "PRACA", "PRACA": "PRACA",
    "PSG": "PASSAGEM", "PASS": "PASSAGEM", "PASSAGEM": "PASSAGEM",
    "LG": "LARGO", "LARGO": "LARGO",
    "VL": "VILA", "VILA": "VILA",
    "VIELA": "VIELA", "BECO": "BECO", "RAMAL": "RAMAL", "VICINAL": "VICINAL",
}
PREPOSICOES = {"DE", "DA", "DO", "DOS", "DAS", "E", "D"}

# Palavras que descrevem o TIPO da escola (e nao QUAL escola e): sao
# removidas para sobrar o "nucleo" do nome. Inclui as siglas de tipo de
# escola mais frequentes nas duas bases, titulos (as bases divergem em
# "PROF JOAO" x "JOAO") e preposicoes.
PALAVRAS_GENERICAS = {
    "ESCOLA", "ESCOLAS", "ESCOLAR", "MUNICIPAL", "ESTADUAL", "FEDERAL", "PARTICULAR", "CONVENIADA",
    "PUBLICA", "PRIVADA", "ENSINO", "FUNDAMENTAL", "MEDIO", "INFANTIL", "BASICA", "EDUCACAO",
    "EDUCACIONAL", "CRECHE", "CENTRO", "UNIDADE", "RURAL", "INDIGENA", "TECNICA", "INTEGRAL",
    "PRE", "DIRETA", "INDIRETA", "DIRET", "INDIR",
    "EMEF", "EMEI", "EMEIF", "EMEIEF", "EMEB", "EMEFM", "EMF", "EM", "EE", "EEEF", "EEEFM", "EEFM",
    "EEF", "EEM", "CEI", "CMEI", "CEMEI", "CEU", "EPG", "ETEC", "CR", "CE", "UE",
    "PROFESSOR", "PROFESSORA", "DOUTOR", "DOUTORA",
    "DE", "DA", "DO", "DOS", "DAS", "E", "A", "O", "AO",
}

COLUNAS_NOVAS = [
    "LATITUDE",
    "LONGITUDE",
    "FONTE_COORDENADA",
    "STATUS_GEOLOCALIZACAO",
    "NIVEL_CASAMENTO",
    "STATUS_CNEFE",
    "MOTIVO_GEOLOCALIZACAO",
    "ALERTAS_GEOLOCALIZACAO",
    "DIST_INEP_CNEFE_KM",
    "INEP_LATITUDE",
    "INEP_LONGITUDE",
    "INEP_ESCOLAS_NO_PONTO",
    "CNEFE_LATITUDE",
    "CNEFE_LONGITUDE",
    "CNEFE_COD_UNICO_ENDERECO",
    "CNEFE_NV_GEO_COORD",
    "CNEFE_DSC_ESTABELECIMENTO",
]

COLUNAS_AUDITORIA = [
    "SG_UF", "CO_MUNICIPIO", "NO_MUNICIPIO",
    "CO_ENTIDADE", "NO_ENTIDADE", "INEP_NOME_NORMALIZADO", "INEP_NUCLEO_NOME",
    "TP_SITUACAO_FUNCIONAMENTO", "TP_LOCALIZACAO",
    "INEP_ENDERECO", "INEP_CEP", "INEP_NUMERO",
    "STATUS_GEOLOCALIZACAO", "FONTE_COORDENADA", "LATITUDE", "LONGITUDE",
    "NIVEL_CASAMENTO", "STATUS_CNEFE", "MOTIVO_GEOLOCALIZACAO", "ALERTAS_GEOLOCALIZACAO",
    "N_CANDIDATOS", "SIMILARIDADE_NOME",
    "CNEFE_COD_UNICO_ENDERECO", "CNEFE_DSC_ESTABELECIMENTO", "CNEFE_NOME_NORMALIZADO", "CNEFE_NUCLEO_NOME",
    "CNEFE_ENDERECO", "CNEFE_CEP", "CNEFE_NUMERO",
    "CNEFE_LATITUDE", "CNEFE_LONGITUDE", "CNEFE_NV_GEO_COORD",
    "INEP_LATITUDE", "INEP_LONGITUDE", "INEP_ESCOLAS_NO_PONTO", "DIST_INEP_CNEFE_KM",
]

COLUNAS_NAO_USADOS = [
    "SG_UF", "COD_MUNICIPIO", "COD_UNICO_ENDERECO", "DSC_ESTABELECIMENTO", "NUCLEO_NOME",
    "ENDERECO", "CEP", "NUM_ENDERECO", "LATITUDE", "LONGITUDE", "NV_GEO_COORD",
]

# Colunas acrescentadas as copias marcadas das duas bases primarias
COLUNAS_MARCADAS_INEP = [
    "NO_CENSO_ESCOLAR_2024", "NIVEL_CASAMENTO", "STATUS_CNEFE", "CNEFE_COD_UNICO_ENDERECO",
    "DIST_INEP_CNEFE_KM", "FONTE_COORDENADA", "STATUS_GEOLOCALIZACAO",
]
COLUNAS_MARCADAS_CNEFE = ["CO_ENTIDADE", "NIVEL_CASAMENTO", "STATUS_CNEFE", "DIST_INEP_CNEFE_KM"]


def cep_generico(cep: str) -> bool:
    """CEPs terminados em "000" costumam ser o CEP-base do municipio, nao do logradouro."""
    return bool(cep) and cep.endswith("000")


def normalizar_cep(cep: str) -> str:
    return cep.zfill(8) if cep else ""


def normalizar_nome(texto: str) -> str:
    """Remove acento/pontuacao e uniformiza caixa para comparar nomes."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    so_alfanumerico = re.sub(r"[^A-Za-z0-9 ]", " ", sem_acento.upper())
    return " ".join(so_alfanumerico.split())


def juntar_letras_soltas(palavras: list) -> list:
    """Junta letras soltas seguidas numa sigla: "E M E F" -> "EMEF".

    O INEP escreve muitas siglas com ponto ("E.M.E.F."), que a remocao de
    pontuacao transforma em letras soltas; o CNEFE costuma escrever "EMEF".
    """
    resultado, letras = [], []
    for palavra in palavras + [""]:
        if len(palavra) == 1 and palavra.isalpha():
            letras.append(palavra)
            continue
        if len(letras) > 1:
            resultado.append("".join(letras))
        else:
            resultado.extend(letras)
        letras = []
        if palavra:
            resultado.append(palavra)
    return resultado


def nucleo_nome(texto: str) -> str:
    """Parte do nome que identifica QUAL escola e, comparavel entre INEP e CNEFE.

    normaliza -> junta letras soltas em sigla -> expande abreviacoes ->
    remove palavras genericas. Ex.: "E.M.E.F. PROF. JOAO DA SILVA" e
    "ESCOLA MUNICIPAL DE ENSINO FUNDAMENTAL PROFESSOR JOAO DA SILVA" viram
    os dois "JOAO SILVA". Vazio quando o nome so tem palavras genericas
    (ex.: "ESCOLA MUNICIPAL") - esses nomes nao identificam escola nenhuma.
    """
    palavras = juntar_letras_soltas(normalizar_nome(texto).split())
    expandidas = []
    for palavra in palavras:
        expandidas.extend(ABREVIACOES.get(palavra, palavra).split())
    return " ".join(p for p in expandidas if p not in PALAVRAS_GENERICAS)


def similaridade_nome(a: str, b: str) -> float:
    """Similaridade por conjunto de palavras (tolera ordem diferente entre as duas bases)."""
    tokens_a = " ".join(sorted(normalizar_nome(a).split()))
    tokens_b = " ".join(sorted(normalizar_nome(b).split()))
    return difflib.SequenceMatcher(None, tokens_a, tokens_b).ratio()


def normalizar_numero(texto: str) -> str:
    """Extrai so os digitos de um numero de endereco; vazio se nao houver ou se for zero.

    No CNEFE, NUM_ENDERECO "0" significa sem numero (S/N). Tratar "0" como
    numero fazia "CEP generico + 0" virar casamento exato (228 casos no PA).
    """
    return re.sub(r"\D", "", texto or "").lstrip("0")


def palavras_logradouro(texto: str) -> tuple:
    """Separa um logradouro em (tipo, conjunto de palavras do nome) para comparar INEP e CNEFE.

    O INEP muitas vezes escreve a rua sem o tipo e com o titulo no fim
    ("HILARIA MARIA SAO LUIZ IRMA"), e o CNEFE com tipo e titulo na frente
    ("RUA IRMA HILARIA MARIA SAO LUIZ"); por isso compara-se o conjunto de
    palavras, sem preposicoes e com abreviacoes expandidas ("DR" ->
    "DOUTOR"). O tipo e vazio quando a primeira palavra nao e um tipo de
    logradouro.
    """
    palavras = normalizar_nome(texto).split()
    tipo = ""
    if palavras and palavras[0] in TIPOS_LOGRADOURO:
        tipo = TIPOS_LOGRADOURO[palavras.pop(0)]
    expandidas = []
    for palavra in palavras:
        expandidas.extend(ABREVIACOES.get(palavra, palavra).split())
    return tipo, frozenset(p for p in expandidas if p not in PREPOSICOES)


def mesmo_logradouro(a: tuple, b: tuple) -> bool:
    """Mesma rua: mesmas palavras do nome e, se as duas bases informam o tipo, o mesmo tipo."""
    (tipo_a, nome_a), (tipo_b, nome_b) = a, b
    if not (nome_a and nome_b) or nome_a != nome_b:
        return False
    return not (tipo_a and tipo_b) or tipo_a == tipo_b


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia em km entre dois pontos (formula de haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def carregar_coordenadas_inep(caminho: Path) -> tuple:
    """Le o cadastro de escolas do INEP (geobr) e devolve (coordenadas, catalogo, colunas_catalogo).

    coordenadas: CO_ENTIDADE -> (lat, lon, escolas_no_ponto). Escolas sem
    geometria no cadastro ficam de fora. escolas_no_ponto conta quantas
    escolas do cadastro inteiro tem exatamente o mesmo ponto (6 casas
    decimais, ~0,1 m), para detectar marcacoes genericas.
    catalogo: o cadastro inteiro sem a geometria, uma lista de dicts com o
    ponto em INEP_LATITUDE/INEP_LONGITUDE, para a copia marcada.
    """
    if not caminho.exists():
        raise SystemExit(
            "cadastro do INEP nao encontrado em {} - rode antes: "
            "ipea_geobr_escolas__baixar_dados.py".format(caminho)
        )
    import geopandas  # so este passo precisa ler GeoPackage

    cadastro = geopandas.read_file(caminho)
    colunas = [c for c in cadastro.columns if c != "geometry"]
    pontos, catalogo = {}, []
    for registro, geometria in zip(cadastro[colunas].astype(object).where(cadastro[colunas].notna(), "")
                                   .to_dict("records"), cadastro.geometry):
        registro["code_school"] = str(int(registro["code_school"]))
        tem_ponto = geometria is not None and not geometria.is_empty
        if tem_ponto:
            pontos[registro["code_school"]] = (round(geometria.y, 6), round(geometria.x, 6))
        lat, lon = pontos[registro["code_school"]] if tem_ponto else ("", "")
        catalogo.append(dict(registro, SG_UF=registro["abbrev_state"], INEP_LATITUDE=lat, INEP_LONGITUDE=lon))
    no_ponto = collections.Counter(pontos.values())
    coordenadas = {codigo: (lat, lon, no_ponto[(lat, lon)]) for codigo, (lat, lon) in pontos.items()}
    return coordenadas, catalogo, ["SG_UF"] + colunas + ["INEP_LATITUDE", "INEP_LONGITUDE"]


def escolher_coordenada(r: dict, inep: tuple) -> dict:
    """Decide a coordenada final de uma escola a partir do casamento com o CNEFE (r) e do ponto do INEP.

    Niveis 1 e 2 (endereco): o ponto do CNEFE, salvo o nivel 2 com CEP
    generico. Demais: o do INEP, salvo se nao existir ou for repetido por
    varias escolas e o CNEFE tiver ponto.
    Devolve as colunas de coordenada final, status, fonte e distancia, e
    acrescenta o alerta ponto_inep_repetido em r["alertas"] quando for o caso.
    """
    registro = r["registro"]
    cnefe = (float(registro["latitude"]), float(registro["longitude"])) if registro else None
    final = {"DIST_INEP_CNEFE_KM": "", "INEP_LATITUDE": "", "INEP_LONGITUDE": "", "INEP_ESCOLAS_NO_PONTO": ""}

    if inep is not None:
        lat, lon, no_ponto = inep
        final.update(INEP_LATITUDE=lat, INEP_LONGITUDE=lon, INEP_ESCOLAS_NO_PONTO=no_ponto)
        if no_ponto >= PONTO_INEP_REPETIDO:
            r["alertas"].append("ponto_inep_repetido")
        if cnefe is not None:
            final["DIST_INEP_CNEFE_KM"] = round(distancia_km(lat, lon, *cnefe), 3)

    endereco_confiavel = r["status"] in NIVEIS_PONTO_CNEFE and not (
        r["status"] == "cep_numero" and "cep_generico" in r["alertas"])
    if cnefe is not None and endereco_confiavel:
        return dict(final, LATITUDE=registro["latitude"], LONGITUDE=registro["longitude"],
                    FONTE_COORDENADA="cnefe", STATUS_GEOLOCALIZACAO=r["status"])
    if inep is not None and not (cnefe is not None and inep[2] >= PONTO_INEP_REPETIDO):
        if cnefe is None:
            status = "inep_sem_cnefe"
        elif final["DIST_INEP_CNEFE_KM"] <= CONFIRMADO_ATE_KM:
            status = "inep_confirmado"
        elif final["DIST_INEP_CNEFE_KM"] <= DIVERGENTE_ACIMA_KM:
            status = "inep_proximo"
        else:
            status = "inep_divergente"
        return dict(final, LATITUDE=inep[0], LONGITUDE=inep[1], FONTE_COORDENADA="inep", STATUS_GEOLOCALIZACAO=status)
    if cnefe is not None:
        return dict(final, LATITUDE=registro["latitude"], LONGITUDE=registro["longitude"],
                    FONTE_COORDENADA="cnefe", STATUS_GEOLOCALIZACAO=r["status"])
    return dict(final, LATITUDE="", LONGITUDE="", FONTE_COORDENADA="", STATUS_GEOLOCALIZACAO="sem_correspondencia")


def endereco_inep(linha: dict) -> str:
    partes = [linha["DS_ENDERECO"], linha["NU_ENDERECO"], linha["DS_COMPLEMENTO"], linha["NO_BAIRRO"]]
    return " - ".join(p.strip() for p in partes if p and p.strip())


def localizar_csv_inep(ano: str) -> Path:
    """Encontra o CSV principal do Censo Escolar ja extraido, buscando pelo nome do arquivo.

    A estrutura interna do ZIP do INEP varia por ano (nome da pasta muda),
    entao procuramos pelo nome do arquivo em vez de fixar o caminho.
    """
    candidatos = sorted(DIR_INEP.glob("**/microdados_ed_basica_{}.csv".format(ano)))
    if not candidatos:
        raise FileNotFoundError(
            "microdados_ed_basica_{}.csv nao encontrado em {} - rode antes: "
            "inep_censo_escolar__baixar_dados.py {} --extrair".format(ano, DIR_INEP, ano)
        )
    return candidatos[0]


def carregar_escolas_inep(caminho_csv: Path, codigos_uf: set) -> tuple:
    """Le o Censo Escolar e devolve {codigo_uf: [linha, ...]} so das UFs pedidas."""
    por_uf = {codigo: [] for codigo in codigos_uf}
    with open(caminho_csv, encoding="latin-1", newline="") as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=";")
        for linha in leitor:
            if linha["CO_UF"] in por_uf:
                por_uf[linha["CO_UF"]].append(linha)
    return por_uf, leitor.fieldnames


def carregar_cnefe_ensino(uf_codigo: str, uf_sigla: str) -> tuple:
    """Le o CNEFE extraido de uma UF e devolve (registros, cabecalho) so dos estabelecimentos de ensino.

    Cada registro guarda tambem a linha original ("linha"), para a copia
    marcada do CNEFE.

    COD_ESPECIE = "4" foi inferido empiricamente (ver
    docs/06-georeferenciamento-escolas.org) - o dicionario oficial do CNEFE
    ainda nao foi lido para confirmar.
    """
    pacote = "{}_{}".format(uf_codigo, uf_sigla.upper())
    caminho = DIR_CNEFE / pacote / "{}.csv".format(pacote)
    if not caminho.exists():
        raise FileNotFoundError(
            "{} nao encontrado - rode antes: ibge_cnefe__baixar_dados.py {} --extrair".format(
                caminho, uf_sigla
            )
        )

    registros = []
    with open(caminho, encoding="latin-1", newline="") as arquivo:
        leitor = csv.reader(arquivo, delimiter=";")
        cabecalho = next(leitor)
        indice = {nome: posicao for posicao, nome in enumerate(cabecalho)}

        for linha in leitor:
            if linha[indice["COD_ESPECIE"]] != "4":
                continue
            logradouro = " ".join(
                linha[indice[coluna]].strip()
                for coluna in ("NOM_TIPO_SEGLOGR", "NOM_TITULO_SEGLOGR", "NOM_SEGLOGR")
                if linha[indice[coluna]].strip()
            )
            partes = [logradouro, linha[indice["NUM_ENDERECO"]], linha[indice["DSC_LOCALIDADE"]]]
            dsc = linha[indice["DSC_ESTABELECIMENTO"]]
            registros.append(
                {
                    "cod_unico": linha[indice["COD_UNICO_ENDERECO"]],
                    "municipio": linha[indice["COD_MUNICIPIO"]],
                    "cep": normalizar_cep(linha[indice["CEP"]]),
                    "numero": normalizar_numero(linha[indice["NUM_ENDERECO"]]),
                    "num_original": linha[indice["NUM_ENDERECO"]],
                    "endereco": " - ".join(p.strip() for p in partes if p and p.strip()),
                    "latitude": linha[indice["LATITUDE"]],
                    "longitude": linha[indice["LONGITUDE"]],
                    "nv_geo_coord": linha[indice["NV_GEO_COORD"]],
                    "dsc_estabelecimento": dsc,
                    "nucleo": nucleo_nome(dsc),
                    "logradouro": palavras_logradouro(logradouro),
                    "linha": linha,
                }
            )
    return registros, cabecalho


def estagio_endereco(escola: dict, idx_exato: dict):
    """Niveis 1 e 2: municipio + CEP + numero, com (endereco_exato) ou sem (cep_numero) a mesma rua.

    Devolve (registro, status, n_candidatos, nota, alertas) ou None.
    """
    cep = normalizar_cep(escola["CO_CEP"])
    numero = normalizar_numero(escola["NU_ENDERECO"])
    if not (cep and numero):
        return None
    candidatos = idx_exato.get((escola["CO_MUNICIPIO"], cep, numero))
    if not candidatos:
        return None

    rua = palavras_logradouro(escola["DS_ENDERECO"])
    mesma_rua = [c for c in candidatos if mesmo_logradouro(rua, c["logradouro"])]
    status = "endereco_exato" if mesma_rua else "cep_numero"
    candidatos = mesma_rua or candidatos

    alertas = []
    if cep_generico(cep):
        alertas.append("cep_generico")
    if len(candidatos) == 1:
        return candidatos[0], status, 1, similaridade_nome(escola["NO_ENTIDADE"], candidatos[0]["dsc_estabelecimento"]), alertas
    # Mesmo endereco exato para todos - a posicao ja esta certa; o nome so
    # decide qual ponto anotar.
    alertas.append("varios_no_endereco")
    nota, escolhido = max(
        ((similaridade_nome(escola["NO_ENTIDADE"], c["dsc_estabelecimento"]), c) for c in candidatos),
        key=lambda par: par[0],
    )
    return escolhido, status, len(candidatos), nota, alertas


def estagio2_por_nome(escolas_inep: list, cnefe: list, resultado: list, usados: set,
                      chave_nome, status: str, registrar_falhas: bool) -> None:
    """Niveis 3 (nome_exato) e 4 (nome_ajustado): nome igual e unico dos dois lados no municipio.

    chave_nome transforma o nome antes de comparar: normalizar_nome no nivel 3
    (so acento, pontuacao e caixa) e nucleo_nome no nivel 4 (abreviacoes
    expandidas e palavras genericas removidas). Preenche resultado[i] das
    escolas ainda sem resultado e acrescenta os pontos escolhidos a usados,
    para que um estagio seguinte nao os reaproveite. Com
    registrar_falhas=False, quem nao casa fica sem resultado para o
    proximo estagio tentar.
    """
    idx_cnefe = {}
    for registro in cnefe:
        chave = chave_nome(registro["dsc_estabelecimento"])
        if chave:
            idx_cnefe.setdefault((registro["municipio"], chave), []).append(registro)
    contagem_inep = collections.Counter(
        (escola["CO_MUNICIPIO"], chave_nome(escola["NO_ENTIDADE"])) for escola in escolas_inep
    )

    for i, escola in enumerate(escolas_inep):
        if resultado[i] is not None:
            continue
        chave = chave_nome(escola["NO_ENTIDADE"])
        candidatos = idx_cnefe.get((escola["CO_MUNICIPIO"], chave), []) if chave else []
        if not chave:
            motivo = "nome_generico"
        elif not candidatos:
            motivo = "nome_nao_encontrado"
        elif contagem_inep[(escola["CO_MUNICIPIO"], chave)] > 1:
            motivo = "nome_repetido_inep"
        elif len(candidatos) > 1:
            motivo = "nome_repetido_cnefe"
        elif candidatos[0]["cod_unico"] in usados:
            motivo = "ponto_ja_usado"
        else:
            resultado[i] = {"registro": candidatos[0], "status": status, "motivo": "", "alertas": [],
                            "n_candidatos": 1,
                            "nota": similaridade_nome(escola["NO_ENTIDADE"], candidatos[0]["dsc_estabelecimento"])}
            usados.add(candidatos[0]["cod_unico"])
            continue
        if registrar_falhas:
            resultado[i] = {"registro": None, "status": "sem_correspondencia", "motivo": motivo, "alertas": [],
                            "n_candidatos": len(candidatos), "nota": None}


def processar_uf(uf_sigla: str, escolas_inep: list, coordenadas_inep: dict) -> tuple:
    """Geolocaliza as escolas de uma UF.

    Devolve (linhas_saida, linhas_auditoria, linhas_nao_usados, linhas_cnefe_marcado,
    colunas_cnefe, contagens).
    """
    uf_codigo = UFS[uf_sigla]
    print("[{}] {} escolas no Censo Escolar {}".format(uf_sigla, len(escolas_inep), ANO_CENSO_ESCOLAR))

    print("    lendo CNEFE de {}...".format(uf_sigla.upper()))
    cnefe, colunas_cnefe = carregar_cnefe_ensino(uf_codigo, uf_sigla)
    print("    {} estabelecimentos de ensino no CNEFE".format(len(cnefe)))

    idx_exato = {}
    for registro in cnefe:
        if registro["cep"] and registro["numero"]:
            idx_exato.setdefault((registro["municipio"], registro["cep"], registro["numero"]), []).append(registro)

    # resultado[i] = dict com registro/status/motivo/alertas/n_candidatos/nota da escola i
    resultado: list = [None] * len(escolas_inep)
    usados = set()

    for i, escola in enumerate(escolas_inep):
        achado = estagio_endereco(escola, idx_exato)
        if achado is not None:
            registro, status, n_candidatos, nota, alertas = achado
            resultado[i] = {"registro": registro, "status": status, "motivo": "", "alertas": alertas,
                            "n_candidatos": n_candidatos, "nota": nota}
            usados.add(registro["cod_unico"])

    # O nivel 3 so registra os acertos; quem falha segue para o 4, que e o
    # ultimo e por isso define o motivo de quem fica sem coordenada.
    estagio2_por_nome(escolas_inep, cnefe, resultado, usados, normalizar_nome, "nome_exato", registrar_falhas=False)
    estagio2_por_nome(escolas_inep, cnefe, resultado, usados, nucleo_nome, "nome_ajustado", registrar_falhas=True)

    usos = collections.Counter(r["registro"]["cod_unico"] for r in resultado if r["registro"] is not None)
    for r in resultado:
        if r["registro"] is not None and usos[r["registro"]["cod_unico"]] > 1:
            r["alertas"].append("ponto_compartilhado")

    linhas_saida, linhas_auditoria = [], []
    contagens = collections.Counter()
    contagens_cnefe = collections.Counter()
    motivos = collections.Counter()
    alertas_total = collections.Counter()
    escolas_no_ponto = collections.defaultdict(list)  # cod_unico do CNEFE -> [(CO_ENTIDADE, status, distancia)]
    for escola, r in zip(escolas_inep, resultado):
        registro = r["registro"] or {}
        final = escolher_coordenada(r, coordenadas_inep.get(escola["CO_ENTIDADE"]))
        contagens[final["STATUS_GEOLOCALIZACAO"]] += 1
        contagens_cnefe[r["status"]] += 1
        if r["motivo"]:
            motivos[r["motivo"]] += 1
        alertas_total.update(r["alertas"])
        if registro:
            escolas_no_ponto[registro["cod_unico"]].append(
                (escola["CO_ENTIDADE"], r["status"], final["DIST_INEP_CNEFE_KM"]))
        geo = dict(
            final,
            NIVEL_CASAMENTO=NIVEL_CASAMENTO.get(r["status"], ""),
            STATUS_CNEFE=r["status"],
            MOTIVO_GEOLOCALIZACAO=r["motivo"],
            ALERTAS_GEOLOCALIZACAO="|".join(r["alertas"]),
            CNEFE_LATITUDE=registro.get("latitude", ""),
            CNEFE_LONGITUDE=registro.get("longitude", ""),
            CNEFE_COD_UNICO_ENDERECO=registro.get("cod_unico", ""),
            CNEFE_NV_GEO_COORD=registro.get("nv_geo_coord", ""),
            CNEFE_DSC_ESTABELECIMENTO=registro.get("dsc_estabelecimento", ""),
        )
        linhas_saida.append(dict(escola, **geo))
        linhas_auditoria.append(dict(
            geo,
            SG_UF=escola["SG_UF"], CO_MUNICIPIO=escola["CO_MUNICIPIO"], NO_MUNICIPIO=escola["NO_MUNICIPIO"],
            CO_ENTIDADE=escola["CO_ENTIDADE"], NO_ENTIDADE=escola["NO_ENTIDADE"],
            INEP_NOME_NORMALIZADO=normalizar_nome(escola["NO_ENTIDADE"]),
            INEP_NUCLEO_NOME=nucleo_nome(escola["NO_ENTIDADE"]),
            TP_SITUACAO_FUNCIONAMENTO=escola["TP_SITUACAO_FUNCIONAMENTO"], TP_LOCALIZACAO=escola["TP_LOCALIZACAO"],
            INEP_ENDERECO=endereco_inep(escola), INEP_CEP=escola["CO_CEP"], INEP_NUMERO=escola["NU_ENDERECO"],
            N_CANDIDATOS=r["n_candidatos"],
            SIMILARIDADE_NOME="{:.3f}".format(r["nota"]) if r["nota"] is not None else "",
            CNEFE_NOME_NORMALIZADO=normalizar_nome(registro.get("dsc_estabelecimento", "")),
            CNEFE_NUCLEO_NOME=registro.get("nucleo", ""), CNEFE_ENDERECO=registro.get("endereco", ""),
            CNEFE_CEP=registro.get("cep", ""), CNEFE_NUMERO=registro.get("num_original", ""),
        ))

    linhas_nao_usados = [
        {
            "SG_UF": uf_sigla.upper(), "COD_MUNICIPIO": c["municipio"], "COD_UNICO_ENDERECO": c["cod_unico"],
            "DSC_ESTABELECIMENTO": c["dsc_estabelecimento"], "NUCLEO_NOME": c["nucleo"], "ENDERECO": c["endereco"],
            "CEP": c["cep"], "NUM_ENDERECO": c["num_original"], "LATITUDE": c["latitude"],
            "LONGITUDE": c["longitude"], "NV_GEO_COORD": c["nv_geo_coord"],
        }
        for c in cnefe
        if c["cod_unico"] not in usos
    ]

    linhas_cnefe_marcado = []
    for c in cnefe:
        ligadas = escolas_no_ponto.get(c["cod_unico"], [])
        linhas_cnefe_marcado.append(dict(
            zip(colunas_cnefe, c["linha"]),
            SG_UF=uf_sigla.upper(),
            CO_ENTIDADE="|".join(codigo for codigo, _, _ in ligadas),
            NIVEL_CASAMENTO="|".join(str(NIVEL_CASAMENTO[status]) for _, status, _ in ligadas),
            STATUS_CNEFE="|".join(status for _, status, _ in ligadas),
            DIST_INEP_CNEFE_KM="|".join(str(dist) for _, _, dist in ligadas),
        ))

    total = len(escolas_inep) or 1
    print("    casamento com o CNEFE:")
    for status in STATUS_CNEFE:
        print("      {:22s} {:6d}  ({:.1f}%)".format(status, contagens_cnefe[status], 100 * contagens_cnefe[status] / total))
    print("    coordenada final:")
    for status in STATUS:
        print("      {:22s} {:6d}  ({:.1f}%)".format(status, contagens[status], 100 * contagens[status] / total))
    for motivo, quantidade in motivos.most_common():
        print("      motivo {:24s} {:6d}".format(motivo, quantidade))
    for alerta, quantidade in alertas_total.most_common():
        print("      alerta {:24s} {:6d}".format(alerta, quantidade))
    print("    pontos do CNEFE usados: {} | nao usados: {} | usados por mais de uma escola: {}".format(
        len(usos), len(linhas_nao_usados), sum(1 for n in usos.values() if n > 1)))
    return linhas_saida, linhas_auditoria, linhas_nao_usados, linhas_cnefe_marcado, colunas_cnefe, contagens


def gravar_mesclando(caminho: Path, colunas: list, linhas_novas: list, ufs_processadas: set) -> None:
    """Grava o CSV mantendo as linhas de UFs que ja estavam nele e nao foram reprocessadas agora.

    Rodar o ETL so para "am pa" nao pode apagar SP de um arquivo que ja
    tinha SP.
    """
    mantidas = []
    if caminho.exists():
        with open(caminho, encoding="utf-8", newline="") as arquivo:
            mantidas = [l for l in csv.DictReader(arquivo, delimiter=";") if l["SG_UF"] not in ufs_processadas]
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    with open(temporario, "w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas, delimiter=";", restval="", extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(mantidas)
        escritor.writerows(linhas_novas)
    temporario.replace(caminho)
    print("{}: {} linhas novas, {} mantidas de outras UFs".format(caminho, len(linhas_novas), len(mantidas)))


def ufs_com_cnefe_baixado() -> list:
    """Lista as siglas de UF que ja tem o CNEFE extraido em data/ibge_cnefe/zipfiles/."""
    if not DIR_CNEFE.exists():
        return []
    encontradas = []
    for pasta in sorted(DIR_CNEFE.iterdir()):
        codigo = pasta.name.split("_", 1)[0]
        if codigo in CODIGO_PARA_SIGLA and (pasta / "{}.csv".format(pasta.name)).exists():
            encontradas.append(CODIGO_PARA_SIGLA[codigo])
    return encontradas


def principal() -> None:
    """Le a linha de comando e roda o ETL para as UFs pedidas (padrao: as que ja tem CNEFE baixado)."""
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument(
        "ufs",
        nargs="*",
        choices=list(UFS) + [[]],
        type=str.lower,
        help="siglas das UFs a processar (padrao: as que ja tem CNEFE extraido)",
    )
    analisador.add_argument(
        "--saida",
        type=Path,
        default=SAIDA_PADRAO,
        help="caminho do CSV de saida (padrao: {})".format(SAIDA_PADRAO),
    )
    analisador.add_argument(
        "--dir-auditoria",
        type=Path,
        default=DIR_AUDITORIA,
        help="pasta dos CSVs de auditoria (padrao: {})".format(DIR_AUDITORIA),
    )
    analisador.add_argument("--listar", action="store_true", help="lista as UFs com CNEFE ja baixado e sai")
    argumentos = analisador.parse_args()

    if argumentos.listar:
        disponiveis = ufs_com_cnefe_baixado()
        if not disponiveis:
            print("nenhuma UF com CNEFE extraido em {}".format(DIR_CNEFE))
        for uf in disponiveis:
            print(uf)
        return

    ufs_pedidas = argumentos.ufs or ufs_com_cnefe_baixado()
    if not ufs_pedidas:
        raise SystemExit(
            "nenhuma UF com CNEFE baixado em {} - rode antes: "
            "ibge_cnefe__baixar_dados.py <uf> --extrair".format(DIR_CNEFE)
        )

    caminho_inep = localizar_csv_inep(ANO_CENSO_ESCOLAR)
    print("Censo Escolar: {}".format(caminho_inep))
    codigos_uf = {UFS[uf] for uf in ufs_pedidas}
    escolas_por_uf, colunas_inep = carregar_escolas_inep(caminho_inep, codigos_uf)
    print("Cadastro de escolas do INEP (coordenadas): {}".format(ARQUIVO_INEP_COORDENADAS))
    coordenadas_inep, catalogo_inep, colunas_catalogo = carregar_coordenadas_inep(ARQUIVO_INEP_COORDENADAS)
    print("    {} escolas com coordenada".format(len(coordenadas_inep)))

    saida, auditoria, nao_usados, cnefe_marcado = [], [], [], []
    colunas_cnefe = []
    contagens_totais = collections.Counter()
    for uf in ufs_pedidas:
        linhas_saida, linhas_auditoria, linhas_nao_usados, linhas_cnefe, colunas_cnefe, contagens = processar_uf(
            uf, escolas_por_uf[UFS[uf]], coordenadas_inep
        )
        saida += linhas_saida
        auditoria += linhas_auditoria
        nao_usados += linhas_nao_usados
        cnefe_marcado += linhas_cnefe
        contagens_totais.update(contagens)

    ufs_processadas = {uf.upper() for uf in ufs_pedidas}

    # Copia marcada do Catalogo do INEP: o resultado de cada escola, pelo codigo
    por_codigo = {linha["CO_ENTIDADE"]: linha for linha in saida}
    inep_marcado = []
    for escola in catalogo_inep:
        if escola["SG_UF"] not in ufs_processadas:
            continue
        linha = por_codigo.get(escola["code_school"])
        marcas = {coluna: linha[coluna] for coluna in COLUNAS_MARCADAS_INEP[1:]} if linha else {}
        inep_marcado.append(dict(escola, NO_CENSO_ESCOLAR_2024="sim" if linha else "nao", **marcas))

    gravar_mesclando(argumentos.saida, list(colunas_inep) + COLUNAS_NOVAS, saida, ufs_processadas)
    gravar_mesclando(
        argumentos.dir_auditoria / "escolas_inep_x_cnefe_{}.csv".format(ANO_CENSO_ESCOLAR),
        COLUNAS_AUDITORIA, auditoria, ufs_processadas,
    )
    gravar_mesclando(
        argumentos.dir_auditoria / "cnefe_ensino_nao_usados_{}.csv".format(ANO_CENSO_ESCOLAR),
        COLUNAS_NAO_USADOS, nao_usados, ufs_processadas,
    )
    gravar_mesclando(SAIDA_INEP_MARCADO, colunas_catalogo + COLUNAS_MARCADAS_INEP, inep_marcado, ufs_processadas)
    gravar_mesclando(SAIDA_CNEFE_MARCADO, ["SG_UF"] + colunas_cnefe + COLUNAS_MARCADAS_CNEFE,
                     cnefe_marcado, ufs_processadas)

    total = sum(contagens_totais.values()) or 1
    print("\nResumo geral ({} UF(s), {} escolas)".format(len(ufs_pedidas), total))
    for status in STATUS:
        print("  {:22s} {:6d}  ({:.1f}%)".format(status, contagens_totais[status], 100 * contagens_totais[status] / total))


if __name__ == "__main__":
    principal()
