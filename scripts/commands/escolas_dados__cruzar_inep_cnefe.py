#!/usr/bin/env python3
"""ETL: cruza o Censo Escolar do INEP com o CNEFE do IBGE e gera escolas_dados.csv.

Le os dados ja baixados por inep_censo_escolar__baixar_dados.py e por
ibge_cnefe__baixar_dados.py (script separado deste - o download nao faz
nenhuma transformacao) e produz uma linha por escola do Censo Escolar,
enriquecida com LATITUDE/LONGITUDE do CNEFE quando uma correspondencia
confiavel e encontrada.

Estrategia de casamento (documentada com os numeros da validacao em
docs/06-georeferenciamento-escolas.org): nome de escola sozinho nao e uma
chave confiavel entre as duas bases (nenhuma tem um ID em comum, e nomes
sao texto livre digitado por pessoas diferentes). Em vez disso, o
casamento e feito em camadas de confianca decrescente, usando endereco
como sinal principal e nome so para desempate:

    alta   - CO_MUNICIPIO+CO_CEP+NU_ENDERECO (INEP) bate exato com
             COD_MUNICIPIO+CEP+NUM_ENDERECO (CNEFE). Candidato unico e
             aceito direto; mais de um candidato no mesmo endereco e
             desempatado por similaridade de nome.
    media  - so CO_MUNICIPIO+CO_CEP bate (numero ausente ou divergente).
             Mesma logica de desempate por nome quando ha mais de um
             candidato.
    baixa  - nenhum candidato por CEP: cai para similaridade de nome
             dentro do mesmo municipio (a estrategia mais fraca, usada so
             como ultimo recurso).
    ambiguo            - o desempate por nome (em qualquer camada acima)
                          nao decidiu com confianca (dois candidatos com
                          nota muito parecida).
    sem_correspondencia - nenhum candidato em nenhuma camada, ou o unico
                          candidato do fallback por nome ficou abaixo do
                          limiar minimo.

Escolas em ambiguo/sem_correspondencia continuam no CSV de saida (o Censo
Escolar do INEP e a lista mestra - nunca perdemos uma escola por falta de
coordenada), só com LATITUDE/LONGITUDE vazias. Estabelecimentos do CNEFE
que não correspondem a nenhuma escola do INEP (faculdades, autoescolas,
prédios que deixaram de ser escola etc.) são descartados sem virar linha
nova - o CNEFE só empresta coordenada, nunca declara a existência de uma
escola.

So o Censo Escolar de 2024 tem endereco completo (2025 removeu esses
campos - ver docs/05-plano-marcadores-escolas-inep.org), entao por
enquanto o cruzamento so funciona com o ano de 2024.

Uso:
    .venv/bin/python scripts/commands/escolas_dados__cruzar_inep_cnefe.py
    .venv/bin/python ... sp
    .venv/bin/python ... --listar
"""

import argparse
import csv
import difflib
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
DIR_INEP = RAIZ / "data" / "inep_censo_escolar" / "zipfiles"
DIR_CNEFE = RAIZ / "data" / "ibge_cnefe" / "zipfiles"
SAIDA_PADRAO = RAIZ / "data" / "escolas_dados.csv"

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

# Limiares empiricos (ver validacao com dados reais de SP em
# docs/06-georeferenciamento-escolas.org): abaixo disso no fallback por
# nome, preferimos ficar sem coordenada a arriscar uma errada; margem
# pequena entre os dois melhores candidatos vira "ambiguo" em vez de
# escolhido por sorte.
LIMIAR_NOME_FALLBACK = 0.5
MARGEM_AMBIGUO = 0.05

COLUNAS_NOVAS = [
    "LATITUDE",
    "LONGITUDE",
    "CNEFE_NV_GEO_COORD",
    "CNEFE_DSC_ESTABELECIMENTO",
    "STATUS_GEOLOCALIZACAO",
    "CONFIANCA_NOME",
]


def normalizar_nome(texto: str) -> str:
    """Remove acento/pontuacao e uniformiza caixa para comparar nomes."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    so_alfanumerico = re.sub(r"[^A-Za-z0-9 ]", " ", sem_acento.upper())
    return " ".join(so_alfanumerico.split())


def similaridade_nome(a: str, b: str) -> float:
    """Similaridade por conjunto de palavras (tolera ordem diferente entre as duas bases)."""
    tokens_a = " ".join(sorted(normalizar_nome(a).split()))
    tokens_b = " ".join(sorted(normalizar_nome(b).split()))
    return difflib.SequenceMatcher(None, tokens_a, tokens_b).ratio()


def normalizar_numero(texto: str) -> str:
    """Extrai so os digitos de um numero de endereco; vazio se nao houver nenhum (ex.: "S/N")."""
    digitos = re.sub(r"\D", "", texto or "")
    return digitos.lstrip("0") or ("0" if digitos else "")


def escolher_por_nome(candidatos: list, nome_escola: str, limiar: float):
    """Escolhe o candidato mais parecido por nome, ou sinaliza ambiguidade.

    Devolve (candidato_ou_None, melhor_nota, ambiguo). Ambiguo quando o
    segundo colocado fica a menos de MARGEM_AMBIGUO do primeiro - nesse
    caso nao escolhemos nenhum, mesmo que o primeiro passe do limiar.
    """
    pontuados = sorted(
        ((similaridade_nome(nome_escola, c["dsc_estabelecimento"]), c) for c in candidatos),
        key=lambda par: -par[0],
    )
    melhor_nota, melhor = pontuados[0]
    if len(pontuados) > 1 and (melhor_nota - pontuados[1][0]) < MARGEM_AMBIGUO:
        return None, melhor_nota, True
    if melhor_nota < limiar:
        return None, melhor_nota, False
    return melhor, melhor_nota, False


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
        i_especie = indice["COD_ESPECIE"]
        i_municipio = indice["COD_MUNICIPIO"]
        i_cep = indice["CEP"]
        i_numero = indice["NUM_ENDERECO"]
        i_lat = indice["LATITUDE"]
        i_lon = indice["LONGITUDE"]
        i_nv_geo = indice["NV_GEO_COORD"]
        i_dsc = indice["DSC_ESTABELECIMENTO"]

        for linha in leitor:
            if linha[i_especie] != "4":
                continue
            registros.append(
                {
                    "municipio": linha[i_municipio],
                    "cep": linha[i_cep].zfill(8) if linha[i_cep] else "",
                    "numero": normalizar_numero(linha[i_numero]),
                    "latitude": linha[i_lat],
                    "longitude": linha[i_lon],
                    "nv_geo_coord": linha[i_nv_geo],
                    "dsc_estabelecimento": linha[i_dsc],
                }
            )
    return registros


def indexar_cnefe(registros: list):
    """Monta os tres indices usados pelas camadas de casamento (exato, so CEP, so municipio)."""
    idx_exato, idx_cep, idx_municipio = {}, {}, {}
    for registro in registros:
        idx_municipio.setdefault(registro["municipio"], []).append(registro)
        if registro["cep"]:
            idx_cep.setdefault((registro["municipio"], registro["cep"]), []).append(registro)
            if registro["numero"]:
                chave = (registro["municipio"], registro["cep"], registro["numero"])
                idx_exato.setdefault(chave, []).append(registro)
    return idx_exato, idx_cep, idx_municipio


def geolocalizar_escola(escola: dict, idx_exato: dict, idx_cep: dict, idx_municipio: dict):
    """Aplica as camadas de confianca (alta -> media -> baixa) e devolve (registro_ou_None, status, nota)."""
    municipio = escola["CO_MUNICIPIO"]
    cep = (escola["CO_CEP"] or "").zfill(8) if escola["CO_CEP"] else ""
    numero = normalizar_numero(escola["NU_ENDERECO"])
    nome = escola["NO_ENTIDADE"]

    if cep and numero:
        candidatos = idx_exato.get((municipio, cep, numero))
        if candidatos:
            if len(candidatos) == 1:
                return candidatos[0], "alta", None
            escolhido, nota, ambiguo = escolher_por_nome(candidatos, nome, limiar=0.0)
            if ambiguo:
                return None, "ambiguo", nota
            return escolhido, "alta", nota

    if cep:
        candidatos = idx_cep.get((municipio, cep))
        if candidatos:
            if len(candidatos) == 1:
                return candidatos[0], "media", None
            escolhido, nota, ambiguo = escolher_por_nome(candidatos, nome, limiar=0.0)
            if ambiguo:
                return None, "ambiguo", nota
            return escolhido, "media", nota

    candidatos = idx_municipio.get(municipio)
    if candidatos:
        escolhido, nota, ambiguo = escolher_por_nome(candidatos, nome, limiar=LIMIAR_NOME_FALLBACK)
        if ambiguo:
            return None, "ambiguo", nota
        if escolhido is not None:
            return escolhido, "baixa", nota
        return None, "sem_correspondencia", nota

    return None, "sem_correspondencia", None


def processar_uf(uf_sigla: str, escolas_inep: list, escritor: csv.DictWriter) -> dict:
    """Geolocaliza as escolas de uma UF e grava as linhas no CSV de saida. Devolve as contagens por status."""
    uf_codigo = UFS[uf_sigla]
    print("[{}] {} escolas no Censo Escolar {}".format(uf_sigla, len(escolas_inep), ANO_CENSO_ESCOLAR))

    print("    lendo CNEFE de {}...".format(uf_sigla.upper()))
    cnefe = carregar_cnefe_ensino(uf_codigo, uf_sigla)
    print("    {} estabelecimentos de ensino no CNEFE".format(len(cnefe)))
    idx_exato, idx_cep, idx_municipio = indexar_cnefe(cnefe)

    contagens = {"alta": 0, "media": 0, "baixa": 0, "ambiguo": 0, "sem_correspondencia": 0}
    for escola in escolas_inep:
        registro, status, nota = geolocalizar_escola(escola, idx_exato, idx_cep, idx_municipio)
        contagens[status] += 1

        linha = dict(escola)
        linha["LATITUDE"] = registro["latitude"] if registro else ""
        linha["LONGITUDE"] = registro["longitude"] if registro else ""
        linha["CNEFE_NV_GEO_COORD"] = registro["nv_geo_coord"] if registro else ""
        linha["CNEFE_DSC_ESTABELECIMENTO"] = registro["dsc_estabelecimento"] if registro else ""
        linha["STATUS_GEOLOCALIZACAO"] = status
        linha["CONFIANCA_NOME"] = "{:.3f}".format(nota) if nota is not None else ""
        escritor.writerow(linha)

    total = len(escolas_inep) or 1
    for status, quantidade in contagens.items():
        print("    {:20s} {:6d}  ({:.1f}%)".format(status, quantidade, 100 * quantidade / total))
    return contagens


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

    argumentos.saida.parent.mkdir(parents=True, exist_ok=True)
    contagens_totais = {"alta": 0, "media": 0, "baixa": 0, "ambiguo": 0, "sem_correspondencia": 0}
    with open(argumentos.saida, "w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(colunas_inep) + COLUNAS_NOVAS, delimiter=";")
        escritor.writeheader()
        for uf in ufs_pedidas:
            contagens = processar_uf(uf, escolas_por_uf[UFS[uf]], escritor)
            for status, quantidade in contagens.items():
                contagens_totais[status] += quantidade

    total = sum(contagens_totais.values()) or 1
    print("\nResumo geral ({} UF(s), {} escolas): {}".format(len(ufs_pedidas), total, argumentos.saida))
    for status, quantidade in contagens_totais.items():
        print("  {:20s} {:6d}  ({:.1f}%)".format(status, quantidade, 100 * quantidade / total))


if __name__ == "__main__":
    principal()
