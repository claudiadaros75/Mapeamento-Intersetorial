#!/usr/bin/env python3
"""ETL: cruza o Censo Escolar do INEP com o CNEFE do IBGE e gera escolas_do_censo_2024_georeferenciadas_com_cnefe_2022.csv.

Le os dados ja baixados por inep_censo_escolar__baixar_dados.py e por
ibge_cnefe__baixar_dados.py (script separado deste - o download nao faz
nenhuma transformacao) e produz uma linha por escola do Censo Escolar,
enriquecida com LATITUDE/LONGITUDE do CNEFE quando uma correspondencia
confiavel e encontrada.

Estrategia de casamento em estagios (decisoes e numeros em
docs/08-mapeamento-intersetorial-nacional-diagnostico-norte.org). A regra
geral e conservadora: escola sem coordenada e melhor que escola no lugar
errado.

    estagio 1 - cep_numero: CO_MUNICIPIO+CO_CEP+NU_ENDERECO (INEP) bate
             exato com COD_MUNICIPIO+CEP+NUM_ENDERECO (CNEFE). O nome nao
             precisa bater. Numero "0" conta como sem numero (no CNEFE "0"
             e "S/N"). Varios pontos no mesmo endereco: escolhe o de nome
             mais parecido (a posicao e a mesma de qualquer forma). Varias
             escolas do INEP no mesmo endereco podem dividir o ponto (mesmo
             predio).
    estagio 2a - nome_exato: para quem o estagio 1 nao resolveu, o nome
             e igual nas duas bases no mesmo municipio, depois de tirar so
             acento, pontuacao e diferenca de maiusculas (normalizar_nome),
             e e unico dos dois lados - um so ponto no CNEFE e uma so
             escola no INEP com aquele nome naquele municipio.
    estagio 2b - nome_ajustado: a mesma regra do 2a, comparando o "nucleo"
             do nome (nucleo_nome: abreviacoes expandidas e palavras
             genericas como ESCOLA/MUNICIPAL/EMEF removidas).
             Nos estagios 2a e 2b um ponto ja usado em estagio anterior
             nao e reaproveitado.
    sem_correspondencia - nenhum estagio resolveu; o motivo (do estagio
             2b, o ultimo) fica em MOTIVO_GEOLOCALIZACAO.

Alertas (ALERTAS_GEOLOCALIZACAO, separados por "|") nao tiram a coordenada,
so marcam o que merece conferencia:

    cep_generico         - estagio 1 com CEP terminado em "000" (CEP-base do
                           municipio): mesmo numero em ruas diferentes pode
                           coincidir.
    varios_no_endereco   - estagio 1 com mais de um ponto do CNEFE no mesmo
                           endereco exato.
    ponto_compartilhado  - o mesmo ponto do CNEFE foi dado a mais de uma
                           escola do INEP.

Saidas:
    data/escolas_do_censo_2024_georeferenciadas_com_cnefe_2022.csv
        todas as colunas do INEP + as colunas de geolocalizacao.
    data/auditoria/escolas_inep_x_cnefe_2024.csv
        uma linha por escola do INEP com o ponto do CNEFE escolhido lado a
        lado (ids, nomes, nucleos, enderecos, estagio, motivo, alertas) -
        e o arquivo para auditar o casamento.
    data/auditoria/cnefe_ensino_nao_usados_2024.csv
        pontos de ensino do CNEFE que nenhuma escola usou.

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
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
DIR_INEP = RAIZ / "data" / "inep_censo_escolar" / "zipfiles"
DIR_CNEFE = RAIZ / "data" / "ibge_cnefe" / "zipfiles"
SAIDA_PADRAO = RAIZ / "data" / "escolas_do_censo_2024_georeferenciadas_com_cnefe_2022.csv"
DIR_AUDITORIA = RAIZ / "data" / "auditoria"

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

STATUS = ["cep_numero", "nome_exato", "nome_ajustado", "sem_correspondencia"]

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
    "CNEFE_COD_UNICO_ENDERECO",
    "CNEFE_NV_GEO_COORD",
    "CNEFE_DSC_ESTABELECIMENTO",
    "STATUS_GEOLOCALIZACAO",
    "MOTIVO_GEOLOCALIZACAO",
    "ALERTAS_GEOLOCALIZACAO",
]

COLUNAS_AUDITORIA = [
    "SG_UF", "CO_MUNICIPIO", "NO_MUNICIPIO",
    "CO_ENTIDADE", "NO_ENTIDADE", "INEP_NOME_NORMALIZADO", "INEP_NUCLEO_NOME",
    "TP_SITUACAO_FUNCIONAMENTO", "TP_LOCALIZACAO",
    "INEP_ENDERECO", "INEP_CEP", "INEP_NUMERO",
    "STATUS_GEOLOCALIZACAO", "MOTIVO_GEOLOCALIZACAO", "ALERTAS_GEOLOCALIZACAO",
    "N_CANDIDATOS", "SIMILARIDADE_NOME",
    "CNEFE_COD_UNICO_ENDERECO", "CNEFE_DSC_ESTABELECIMENTO", "CNEFE_NOME_NORMALIZADO", "CNEFE_NUCLEO_NOME",
    "CNEFE_ENDERECO", "CNEFE_CEP", "CNEFE_NUMERO",
    "LATITUDE", "LONGITUDE", "CNEFE_NV_GEO_COORD",
]

COLUNAS_NAO_USADOS = [
    "SG_UF", "COD_MUNICIPIO", "COD_UNICO_ENDERECO", "DSC_ESTABELECIMENTO", "NUCLEO_NOME",
    "ENDERECO", "CEP", "NUM_ENDERECO", "LATITUDE", "LONGITUDE", "NV_GEO_COORD",
]


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


def carregar_cnefe_ensino(uf_codigo: str, uf_sigla: str) -> list:
    """Le o CNEFE extraido de uma UF e devolve so os enderecos de estabelecimento de ensino.

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
                }
            )
    return registros


def estagio1_cep_numero(escola: dict, idx_exato: dict):
    """Estagio 1: municipio + CEP + numero. Devolve (registro, n_candidatos, nota, alertas) ou None."""
    cep = normalizar_cep(escola["CO_CEP"])
    numero = normalizar_numero(escola["NU_ENDERECO"])
    if not (cep and numero):
        return None
    candidatos = idx_exato.get((escola["CO_MUNICIPIO"], cep, numero))
    if not candidatos:
        return None

    alertas = []
    if cep_generico(cep):
        alertas.append("cep_generico")
    if len(candidatos) == 1:
        return candidatos[0], 1, similaridade_nome(escola["NO_ENTIDADE"], candidatos[0]["dsc_estabelecimento"]), alertas
    # Mesmo endereco exato para todos - a posicao ja esta certa; o nome so
    # decide qual ponto anotar.
    alertas.append("varios_no_endereco")
    nota, escolhido = max(
        ((similaridade_nome(escola["NO_ENTIDADE"], c["dsc_estabelecimento"]), c) for c in candidatos),
        key=lambda par: par[0],
    )
    return escolhido, len(candidatos), nota, alertas


def estagio2_por_nome(escolas_inep: list, cnefe: list, resultado: list, usados: set,
                      chave_nome, status: str, registrar_falhas: bool) -> None:
    """Estagio 2 (2a nome_exato / 2b nome_ajustado): nome igual e unico dos dois lados no municipio.

    chave_nome transforma o nome antes de comparar: normalizar_nome no 2a
    (so acento, pontuacao e caixa) e nucleo_nome no 2b (abreviacoes
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


def processar_uf(uf_sigla: str, escolas_inep: list) -> tuple:
    """Geolocaliza as escolas de uma UF. Devolve (linhas_saida, linhas_auditoria, linhas_nao_usados, contagens)."""
    uf_codigo = UFS[uf_sigla]
    print("[{}] {} escolas no Censo Escolar {}".format(uf_sigla, len(escolas_inep), ANO_CENSO_ESCOLAR))

    print("    lendo CNEFE de {}...".format(uf_sigla.upper()))
    cnefe = carregar_cnefe_ensino(uf_codigo, uf_sigla)
    print("    {} estabelecimentos de ensino no CNEFE".format(len(cnefe)))

    idx_exato = {}
    for registro in cnefe:
        if registro["cep"] and registro["numero"]:
            idx_exato.setdefault((registro["municipio"], registro["cep"], registro["numero"]), []).append(registro)

    # resultado[i] = dict com registro/status/motivo/alertas/n_candidatos/nota da escola i
    resultado: list = [None] * len(escolas_inep)
    usados = set()

    for i, escola in enumerate(escolas_inep):
        achado = estagio1_cep_numero(escola, idx_exato)
        if achado is not None:
            registro, n_candidatos, nota, alertas = achado
            resultado[i] = {"registro": registro, "status": "cep_numero", "motivo": "", "alertas": alertas,
                            "n_candidatos": n_candidatos, "nota": nota}
            usados.add(registro["cod_unico"])

    # Estagio 2a so registra os acertos; quem falha segue para o 2b, que e
    # o ultimo e por isso define o motivo de quem fica sem coordenada.
    estagio2_por_nome(escolas_inep, cnefe, resultado, usados, normalizar_nome, "nome_exato", registrar_falhas=False)
    estagio2_por_nome(escolas_inep, cnefe, resultado, usados, nucleo_nome, "nome_ajustado", registrar_falhas=True)

    usos = collections.Counter(r["registro"]["cod_unico"] for r in resultado if r["registro"] is not None)
    for r in resultado:
        if r["registro"] is not None and usos[r["registro"]["cod_unico"]] > 1:
            r["alertas"].append("ponto_compartilhado")

    linhas_saida, linhas_auditoria = [], []
    contagens = collections.Counter()
    motivos = collections.Counter()
    alertas_total = collections.Counter()
    for escola, r in zip(escolas_inep, resultado):
        registro = r["registro"] or {}
        contagens[r["status"]] += 1
        if r["motivo"]:
            motivos[r["motivo"]] += 1
        alertas_total.update(r["alertas"])
        geo = {
            "LATITUDE": registro.get("latitude", ""),
            "LONGITUDE": registro.get("longitude", ""),
            "CNEFE_COD_UNICO_ENDERECO": registro.get("cod_unico", ""),
            "CNEFE_NV_GEO_COORD": registro.get("nv_geo_coord", ""),
            "CNEFE_DSC_ESTABELECIMENTO": registro.get("dsc_estabelecimento", ""),
            "STATUS_GEOLOCALIZACAO": r["status"],
            "MOTIVO_GEOLOCALIZACAO": r["motivo"],
            "ALERTAS_GEOLOCALIZACAO": "|".join(r["alertas"]),
        }
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

    total = len(escolas_inep) or 1
    for status in STATUS:
        print("    {:22s} {:6d}  ({:.1f}%)".format(status, contagens[status], 100 * contagens[status] / total))
    for motivo, quantidade in motivos.most_common():
        print("      motivo {:24s} {:6d}".format(motivo, quantidade))
    for alerta, quantidade in alertas_total.most_common():
        print("      alerta {:24s} {:6d}".format(alerta, quantidade))
    print("    pontos do CNEFE usados: {} | nao usados: {} | usados por mais de uma escola: {}".format(
        len(usos), len(linhas_nao_usados), sum(1 for n in usos.values() if n > 1)))
    return linhas_saida, linhas_auditoria, linhas_nao_usados, contagens


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

    saida, auditoria, nao_usados = [], [], []
    contagens_totais = collections.Counter()
    for uf in ufs_pedidas:
        linhas_saida, linhas_auditoria, linhas_nao_usados, contagens = processar_uf(uf, escolas_por_uf[UFS[uf]])
        saida += linhas_saida
        auditoria += linhas_auditoria
        nao_usados += linhas_nao_usados
        contagens_totais.update(contagens)

    ufs_processadas = {uf.upper() for uf in ufs_pedidas}
    gravar_mesclando(argumentos.saida, list(colunas_inep) + COLUNAS_NOVAS, saida, ufs_processadas)
    gravar_mesclando(
        argumentos.dir_auditoria / "escolas_inep_x_cnefe_{}.csv".format(ANO_CENSO_ESCOLAR),
        COLUNAS_AUDITORIA, auditoria, ufs_processadas,
    )
    gravar_mesclando(
        argumentos.dir_auditoria / "cnefe_ensino_nao_usados_{}.csv".format(ANO_CENSO_ESCOLAR),
        COLUNAS_NAO_USADOS, nao_usados, ufs_processadas,
    )

    total = sum(contagens_totais.values()) or 1
    print("\nResumo geral ({} UF(s), {} escolas)".format(len(ufs_pedidas), total))
    for status in STATUS:
        print("  {:22s} {:6d}  ({:.1f}%)".format(status, contagens_totais[status], 100 * contagens_totais[status] / total))


if __name__ == "__main__":
    principal()
