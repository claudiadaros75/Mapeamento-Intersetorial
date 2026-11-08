"""Normalizadores compartilhados do pareamento INEP x CNEFE (modulo, nao e comando).

Os quatro niveis de pareamento (docs/features/mapa-escolas-inep-cnefe.org)
so funcionam se as duas bases forem normalizadas *exatamente da mesma
forma*: uma diferenca aqui vira um falso "sem par" que nenhum nivel corrige.
Por isso tudo que transforma texto para comparacao mora neste arquivo,
coberto por test_escolas_normalizacao.py.

Conteudo:
    normalizar_texto      - sem acento/pontuacao, caixa alta, espacos unicos
    normalizar_cep        - 8 digitos ou vazio; cep_generico() detecta CEP de municipio
    normalizar_numero     - digitos sem zero a esquerda; "S/N", "SN", "0" -> vazio
    normalizar_logradouro - tira tipo (RUA, AV...) e expande titulos (PROF, DR...)
    parse_endereco_inep   - separa o campo "Endereço" do Catalogo de Escolas
    nome_escola_exato     - nome para o nivel N3 (so normalizado)
    nome_escola_nucleo    - nome para o nivel N4 (abreviacoes expandidas, termos genericos removidos)
    haversine_m           - distancia em metros entre duas coordenadas
"""

import math
import re
import unicodedata

# ---------------------------------------------------------------- texto


def normalizar_texto(texto: str) -> str:
    """Remove acento e pontuacao, poe em caixa alta e colapsa espacos."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    so_alfanumerico = re.sub(r"[^A-Z0-9 ]", " ", sem_acento.upper())
    return " ".join(so_alfanumerico.split())


def _expandir(tokens: list, tabela: dict) -> list:
    """Troca cada token pela expansao da tabela (que pode ter varias palavras)."""
    saida = []
    for token in tokens:
        saida.extend(tabela.get(token, token).split())
    return saida


STOPWORDS = {"DE", "DA", "DO", "DAS", "DOS", "E", "D"}

# ---------------------------------------------------------------- CEP / numero


def normalizar_cep(texto: str) -> str:
    """Devolve o CEP com 8 digitos, ou vazio se nao houver 8 digitos."""
    digitos = re.sub(r"\D", "", texto or "")
    if not digitos:
        return ""
    digitos = digitos.zfill(8)
    return digitos if len(digitos) == 8 else ""


def cep_generico(cep: str) -> bool:
    """CEP terminado em 000 costuma ser o CEP-base do municipio, nao o da rua."""
    return bool(cep) and cep.endswith("000")


def normalizar_numero(texto: str) -> str:
    """Numero do endereco so com digitos e sem zero a esquerda; vazio para S/N, SN, 0 ou ausente."""
    digitos = re.sub(r"\D", "", texto or "")
    digitos = digitos.lstrip("0")
    return digitos


# ---------------------------------------------------------------- logradouro

# Tipos de logradouro (abreviados ou nao) que sao removidos do inicio: o
# CNEFE guarda o tipo em coluna separada e o INEP grafa de varias formas
# (R, R., RUA), entao comparar so o nome evita falso negativo.
TIPOS_LOGRADOURO = {
    "R", "RUA", "AV", "AVE", "AVN", "AVENIDA", "TV", "TRV", "TRAV", "TRAVESSA",
    "AL", "ALAMEDA", "EST", "ESTR", "ESTRADA", "ROD", "RODOVIA", "PC", "PCA", "PRACA",
    "LGO", "LARGO", "BC", "BECO", "VIA", "VIELA", "VL", "PRQ", "PARQUE", "LD", "LADEIRA",
    "PS", "PASSAGEM", "SERV", "SERVIDAO", "QD", "QUADRA", "CONJ", "CONJUNTO", "RES",
    "RESIDENCIAL", "SITIO", "FAZ", "FAZENDA", "POV", "POVOADO", "LOT", "LOTEAMENTO",
    "ACESSO", "CAMINHO", "CORREGO", "LINHA", "RAMAL", "VICINAL", "AREA", "SETOR",
    # vistos no DF e em zona rural (v2): o CNEFE grava "EDF"/"NUCLEO" como tipo
    "EDF", "EDIFICIO", "NUCLEO", "ST", "Q",
}
# Sem abreviacoes de uma letra (S, N, D): ruas de loteamento se chamam
# "RUA D", "RUA N" e seriam desfiguradas.
TITULOS = {
    "PROF": "PROFESSOR", "PROFA": "PROFESSORA",
    "DR": "DOUTOR", "DRA": "DOUTORA", "DES": "DESEMBARGADOR", "ENG": "ENGENHEIRO",
    "GAL": "GENERAL", "GEN": "GENERAL", "CEL": "CORONEL", "CAP": "CAPITAO",
    "TEN": "TENENTE", "SGT": "SARGENTO", "MAL": "MARECHAL", "ALM": "ALMIRANTE",
    "PE": "PADRE", "PDE": "PADRE", "FR": "FREI", "STA": "SANTA", "STO": "SANTO",
    "SR": "SENHOR", "SRA": "SENHORA", "PRES": "PRESIDENTE", "GOV": "GOVERNADOR",
    "SEN": "SENADOR", "DEP": "DEPUTADO", "VER": "VEREADOR", "MONS": "MONSENHOR",
    "VISC": "VISCONDE", "BR": "BARAO", "CDE": "CONDE", "CMTE": "COMANDANTE",
    "MAJ": "MAJOR", "BRIG": "BRIGADEIRO", "MIN": "MINISTRO",
}


def normalizar_logradouro(texto: str) -> str:
    """Logradouro comparavel entre as bases: sem tipo no inicio, titulos expandidos, sem stopwords.

    Ex.: "AV. PROF. JOSE DA SILVA" e ("AVENIDA", "PROFESSOR", "JOSE DA SILVA") -> "PROFESSOR JOSE SILVA".
    """
    tokens = normalizar_texto(texto).split()
    while len(tokens) > 1 and tokens[0] in TIPOS_LOGRADOURO:
        tokens = tokens[1:]
    tokens = [TITULOS.get(t, t) for t in tokens]
    # "RUA D" / "RUA E": a letra e o nome da rua, nao uma stopword.
    sem_stopwords = [t for t in tokens if t not in STOPWORDS]
    return " ".join(sem_stopwords or tokens)


def logradouro_cnefe(tipo: str, titulo: str, nome: str) -> str:
    """Monta o logradouro do CNEFE (colunas separadas) no mesmo formato de normalizar_logradouro."""
    return normalizar_logradouro(" ".join(p for p in (tipo, titulo, nome) if p))


# ---------------------------------------------------------------- endereco do INEP

# "LOGRADOURO, [NUMERO] [COMPLEMENTO.] [BAIRRO.] 00000-000 Municipio - UF."
_RE_ENDERECO = re.compile(
    r"^(?P<logradouro>[^,]*),\s*(?P<resto>.*?)\s*(?P<cep>\d{5}-\d{3})\s+(?P<municipio>.+?)\s+-\s+(?P<uf>[A-Z]{2})\.?\s*$"
)
_RE_NUMERO = re.compile(r"^(?:(?P<num>\d+[A-Z]?)|S\s*/?\s*N|SN)\b\.?\s*(?P<depois>.*)$", re.I)


def parse_endereco_inep(endereco: str) -> dict:
    """Separa o campo "Endereço" do Catalogo de Escolas em partes.

    Devolve dict com logradouro, numero, complemento, bairro, cep, municipio,
    uf e ok (False quando o texto nao segue o formato esperado - nesse caso
    so cep/municipio/uf podem ter sido recuperados).
    """
    vazio = {"logradouro": "", "numero": "", "complemento": "", "bairro": "",
             "cep": "", "municipio": "", "uf": "", "ok": False}
    texto = " ".join((endereco or "").split())
    casamento = _RE_ENDERECO.match(texto)
    if not casamento:
        cep = re.search(r"\d{5}-\d{3}", texto)
        vazio["cep"] = normalizar_cep(cep.group(0)) if cep else ""
        return vazio

    resto = casamento.group("resto").strip()
    numero = ""
    m_num = _RE_NUMERO.match(resto)
    if m_num:
        numero = normalizar_numero(m_num.group("num") or "")
        resto = m_num.group("depois")
    segmentos = [s.strip() for s in resto.split(".") if s.strip()]
    bairro = segmentos[-1] if segmentos else ""
    complemento = " ".join(segmentos[:-1])

    return {
        "logradouro": casamento.group("logradouro").strip(),
        "numero": numero,
        "complemento": complemento,
        "bairro": bairro,
        "cep": normalizar_cep(casamento.group("cep")),
        "municipio": casamento.group("municipio").strip(),
        "uf": casamento.group("uf"),
        "ok": True,
    }


# ---------------------------------------------------------------- nome da escola

ABREVIACOES_ESCOLA = {
    "EE": "ESCOLA ESTADUAL", "EEE": "ESCOLA ESTADUAL", "E": "ESCOLA",
    "EM": "ESCOLA MUNICIPAL", "ESC": "ESCOLA", "ESCOL": "ESCOLA",
    "EMEF": "ESCOLA MUNICIPAL ENSINO FUNDAMENTAL", "EMEI": "ESCOLA MUNICIPAL EDUCACAO INFANTIL",
    "EMEIEF": "ESCOLA MUNICIPAL EDUCACAO INFANTIL ENSINO FUNDAMENTAL",
    "EMEB": "ESCOLA MUNICIPAL EDUCACAO BASICA", "EEEF": "ESCOLA ESTADUAL ENSINO FUNDAMENTAL",
    "EEEM": "ESCOLA ESTADUAL ENSINO MEDIO", "EEEFM": "ESCOLA ESTADUAL ENSINO FUNDAMENTAL MEDIO",
    "EMEFM": "ESCOLA MUNICIPAL ENSINO FUNDAMENTAL MEDIO", "EMI": "ESCOLA MUNICIPAL INFANTIL",
    "CEI": "CENTRO EDUCACAO INFANTIL", "CMEI": "CENTRO MUNICIPAL EDUCACAO INFANTIL",
    "CEMEI": "CENTRO MUNICIPAL EDUCACAO INFANTIL", "CRECHE": "CRECHE",
    "CE": "CENTRO EDUCACIONAL", "CEF": "CENTRO ENSINO FUNDAMENTAL", "CED": "CENTRO EDUCACIONAL",
    "CEM": "CENTRO ENSINO MEDIO", "COL": "COLEGIO", "CEEJA": "CENTRO ESTADUAL EDUCACAO JOVENS ADULTOS",
    "UEB": "UNIDADE ESCOLAR BASICA", "UE": "UNIDADE ESCOLAR", "UI": "UNIDADE INTEGRADA",
    "ETEC": "ESCOLA TECNICA", "FATEC": "FACULDADE TECNOLOGIA", "IF": "INSTITUTO FEDERAL",
    "NS": "NOSSA SENHORA", "N": "NOSSA", "SRA": "SENHORA", "STA": "SANTA", "STO": "SANTO",
    "S": "SAO", "PROF": "PROFESSOR", "PROFA": "PROFESSORA", "PROFESSORA": "PROFESSOR",
    "DR": "DOUTOR", "DRA": "DOUTOR", "DOUTORA": "DOUTOR", "PE": "PADRE", "MONS": "MONSENHOR",
    "GOV": "GOVERNADOR", "PRES": "PRESIDENTE", "DEP": "DEPUTADO", "SEN": "SENADOR",
    "VER": "VEREADOR", "CEL": "CORONEL", "MAL": "MARECHAL", "GAL": "GENERAL", "GEN": "GENERAL",
    "MUN": "MUNICIPAL", "EST": "ESTADUAL", "ENS": "ENSINO", "FUND": "FUNDAMENTAL",
    "ED": "EDUCACAO", "EDUC": "EDUCACAO", "INF": "INFANTIL", "PROFISSIONALIZ": "PROFISSIONALIZANTE",
    "I": "1", "II": "2", "III": "3", "IV": "4", "V": "5",
}

# Palavras que descrevem o *tipo* de escola e nao a identificam: o CNEFE
# frequentemente grava so o "nucleo" ("ANTONIO FERREIRA DE SOUZA") enquanto o
# INEP grava o nome completo ("EE PROF ANTONIO FERREIRA DE SOUZA").
TERMOS_GENERICOS_ESCOLA = {
    "ESCOLA", "ESCOLAS", "ESTADUAL", "MUNICIPAL", "FEDERAL", "PARTICULAR", "PRIVADA", "PUBLICA",
    "ENSINO", "FUNDAMENTAL", "MEDIO", "INFANTIL", "BASICA", "EDUCACAO", "EDUCACIONAL",
    "CENTRO", "COLEGIO", "CRECHE", "PRE", "UNIDADE", "ESCOLAR", "INTEGRADA", "INTEGRAL",
    "TEMPO", "JOVENS", "ADULTOS", "PROFESSOR", "DOUTOR", "PADRE", "MONSENHOR", "GOVERNADOR",
    "PRESIDENTE", "DEPUTADO", "SENADOR", "VEREADOR", "CORONEL", "MARECHAL", "GENERAL",
    "NUCLEO", "INSTITUTO", "TECNICA", "CICLO", "GRAU", "SERIE",
    "ANOS", "INICIAIS", "FINAIS", "REGULAR", "DE", "DA", "DO", "DAS", "DOS", "E", "D",
}


# Siglas de tipo de escola fora de ABREVIACOES_ESCOLA (v3): as mais frequentes
# como palavra do nome no catalogo (>= 30 ocorrencias, contadas em 2026-11-07),
# tirando palavras reais (CRESCER, ESTER, CURUMIM, CRISPIM, EU). Lista
# explicita em vez de regex: um regex apagava nomes que SAO siglas (CETES).
SIGLAS_TIPO_ESCOLA = {
    "EMEIF", "EF", "EEF", "CR", "EEI", "EEB", "EEIEF", "EEIF", "CEIM", "CM", "CIEP", "EI", "CEU",
    "ESP", "EC", "CETI", "EEMTI", "EEM", "EMC", "EMUEF", "CMEF", "EBM", "ERM", "ECIT", "EB", "ECI",
    "ER", "EEEP", "CEC", "EMTI", "EMEFI", "EEUEF", "CME", "CI", "CESEC", "EMEFEI", "CEMEB", "EIEF",
    "EEFM", "EIEEF", "EEC", "EPP", "CEPI", "EEFTI", "EMEFTI", "EMPEF", "CEP", "CEIC", "CFP", "CCI",
    "EMR", "ETI", "EPM", "CP", "EMEFS", "CER", "EEP", "EMPEIEF", "CMEB", "EEBM", "EEPEF", "CIEI",
    "EMF", "EFM", "EEIP",
}


def _juntar_letras_soltas(tokens: list) -> list:
    """Junta sequencias de 2+ letras isoladas: "E M E I" -> "EMEI", "E E" -> "EE" (v2)."""
    saida, run = [], []
    for token in tokens + [""]:
        if len(token) == 1 and token.isalpha():
            run.append(token)
            continue
        if len(run) >= 2:
            saida.append("".join(run))
        else:
            saida.extend(run)
        run = []
        if token:
            saida.append(token)
    return saida


def nome_escola_exato(nome: str) -> str:
    """Nome para o nivel N3: so normalizacao de acento, pontuacao, caixa e espacos."""
    return normalizar_texto(nome)


def _tokens_nucleo(nome: str) -> tuple:
    """(tokens expandidos, tokens do nucleo) - base de nome_escola_nucleo e nome_escola_generico."""
    tokens = _expandir(_juntar_letras_soltas(normalizar_texto(nome).split()), ABREVIACOES_ESCOLA)
    # v2: fora tambem codigos numericos ("0918611 CM ...") e siglas de tipo de
    # escola que nao estao na tabela de expansao (EEIEF, CEIM, CM...).
    nucleo = [
        t for t in tokens
        if t not in TERMOS_GENERICOS_ESCOLA
        and not (t.isdigit() and len(t) >= 5)
        and t not in SIGLAS_TIPO_ESCOLA
    ]
    return tokens, nucleo


def nome_escola_generico(nome: str) -> bool:
    """True quando o nome so descreve o tipo ("ESCOLA MUNICIPAL", "CRECHE", "EMEF").

    Um nome generico nao confirma nem contradiz um par feito por endereco (v3).
    """
    return not _tokens_nucleo(nome)[1]


def nome_escola_nucleo(nome: str) -> str:
    """Nome para o nivel N4: abreviacoes expandidas e termos genericos de tipo de escola removidos.

    Se a remocao esvaziar o nome (ex.: "ESCOLA MUNICIPAL"), devolve o nome
    expandido inteiro para nao comparar strings vazias.
    """
    tokens, nucleo = _tokens_nucleo(nome)
    return " ".join(nucleo) if nucleo else " ".join(tokens)


# ---------------------------------------------------------------- distancia

RAIO_TERRA_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia em metros, sobre a esfera, entre dois pontos em graus decimais."""
    fi1, fi2 = math.radians(lat1), math.radians(lat2)
    dfi = fi2 - fi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dfi / 2) ** 2 + math.cos(fi1) * math.cos(fi2) * math.sin(dlambda / 2) ** 2
    return 2 * RAIO_TERRA_M * math.asin(math.sqrt(a))


def faixa_distancia(metros: float) -> str:
    """Faixa usada nos relatorios e no filtro do mapa."""
    if metros < 50:
        return "a_<50m"
    if metros < 200:
        return "b_50-200m"
    if metros < 1000:
        return "c_200m-1km"
    if metros < 5000:
        return "d_1-5km"
    return "e_>5km"
