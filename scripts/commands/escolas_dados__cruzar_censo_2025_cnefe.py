#!/usr/bin/env python3
"""Casamento com o CNEFE 2022 para as escolas do Censo Escolar 2025 (juntado ao Catalogo de Escolas).

Aplica o mesmo algoritmo do ETL do Censo 2024
(escolas_dados__cruzar_inep_cnefe.py: niveis 1 a 4 de casamento com o
CNEFE e a mesma escolha da coordenada final) sobre a base gerada por
inep_censo_escolar__juntar_cadastro_escolar.py:

    entrada: data/inep_censo_escolar_2025_+_cadastro_escolar_do_inep.csv
    saida:   data/inep_+cnef.csv

Os microdados de 2025 nao trazem endereco. Ele vem do Catalogo, num campo
so ("Endereço"), no formato

    LOGRADOURO, NUMERO [COMPLEMENTO]. [BAIRRO]. CEP Municipio - UF.

com partes opcionais. separar_endereco() o divide nas colunas que o ETL
usa (DS_ENDERECO, NU_ENDERECO, DS_COMPLEMENTO, NO_BAIRRO, CO_CEP), que
entram na saida antes das colunas de geolocalizacao. Para o casamento so
pesam CEP, numero e logradouro; complemento e bairro so aparecem no texto
do endereco. Medido contra os campos separados do Censo 2024 (AM, PA, SP;
50.137 escolas nas duas bases): CEP igual em 92,4%, numero em 97,2%,
logradouro em 91,2% - o resto e, na maioria, endereco que mudou no
cadastro (ver docs/features/casamento-cnefe-censo-2025.md).

O ponto do INEP vem das colunas Latitude/Longitude da propria entrada
(o Catalogo), e a contagem de escolas no mesmo ponto usa o Brasil todo,
como no ETL.

Nenhum dado se perde: a saida tem todas as colunas da entrada (todas as
escolas, inclusive as so do Censo ou so do Cadastro), as colunas de
geolocalizacao do ETL e, quando a escola casa com um ponto do CNEFE (niveis
1 a 4, mesmo que a coordenada final seja a do INEP), a linha original do
CNEFE inteira, com o prefixo CNEFE_.

Campos de rastreio (o que aconteceu com o registro):

    JUNCAO_CENSO_CADASTRO   censo_e_cadastro, so_censo, so_cadastro (da entrada)
    ENDERECO_SEPARACAO      cep_e_numero (pode tentar os niveis 1 e 2),
                            sem_numero, sem_cep, sem_cep_e_numero,
                            sem_endereco (escola so do Censo)
    NIVEL_CASAMENTO, STATUS_CNEFE, MOTIVO_GEOLOCALIZACAO, ALERTAS_GEOLOCALIZACAO,
    STATUS_GEOLOCALIZACAO, FONTE_COORDENADA, DIST_INEP_CNEFE_KM
                            os mesmos do ETL de 2024
    N_CANDIDATOS, SIMILARIDADE_NOME, INEP_NOME_NORMALIZADO, INEP_NUCLEO_NOME,
    CNEFE_NOME_NORMALIZADO, CNEFE_NUCLEO_NOME, CNEFE_ENDERECO
                            os campos que o ETL so grava na auditoria
    CNEFE_JUNTADO           sim/nao: a linha do CNEFE entrou no registro
    HISTORICO_PROCESSAMENTO as etapas em ordem, num texto curto

Uso:
    .venv/bin/python scripts/commands/escolas_dados__cruzar_censo_2025_cnefe.py
    .venv/bin/python ... am pa
    .venv/bin/python ... --entrada outro.csv --saida outro.csv
"""

import argparse
import collections
import csv
import re
import sys
from pathlib import Path

# Reaproveita o ETL do Censo 2024: o algoritmo e um so para os dois anos.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import escolas_dados__cruzar_inep_cnefe as etl  # noqa: E402

ANO = "2025"
ENTRADA = etl.RAIZ / "data" / "inep_censo_escolar_{}_+_cadastro_escolar_do_inep.csv".format(ANO)
SAIDA = etl.RAIZ / "data" / "inep_+cnef.csv"

COLUNAS_ENDERECO = ["DS_ENDERECO", "NU_ENDERECO", "DS_COMPLEMENTO", "NO_BAIRRO", "CO_CEP"]

# Colunas de rastreio: o que aconteceu com o registro em cada etapa
COLUNA_JUNCAO = "JUNCAO_CENSO_CADASTRO"  # vem da entrada
COLUNAS_RASTREIO = ["ENDERECO_SEPARACAO", "CNEFE_JUNTADO", "HISTORICO_PROCESSAMENTO"]
# Campos que o ETL so grava no CSV de auditoria
COLUNAS_DA_AUDITORIA = ["N_CANDIDATOS", "SIMILARIDADE_NOME", "INEP_NOME_NORMALIZADO", "INEP_NUCLEO_NOME",
                        "CNEFE_NOME_NORMALIZADO", "CNEFE_NUCLEO_NOME", "CNEFE_ENDERECO"]

# "... 76824-556 Porto Velho - RO." no fim do endereco
FIM_ENDERECO = re.compile(r"\s*(\d{5}-?\d{3})\s+(.*?)\s+-\s+([A-Z]{2})\.?\s*$")
SEM_NUMERO = {"SN", "S/N", "S/Nº", "S/NO", "S.N", "S/N."}
PREFIXO_NUMERO = {"N", "Nº", "NO", "N.", "NR", "KM"}


def comeca_com_numero(texto: str):
    """Se o texto comeca por um numero de endereco, devolve (numero, resto); senao None.

    Numero: um token com digito ("107", "1111-A", "N55"), "S/N" e variantes,
    ou prefixo + digitos ("KM 35", "N 21").
    """
    tokens = texto.split()
    if not tokens:
        return None
    if re.search(r"\d", tokens[0]) or tokens[0].upper() in SEM_NUMERO:
        return tokens[0], " ".join(tokens[1:])
    if len(tokens) > 1 and tokens[0].upper() in PREFIXO_NUMERO and re.match(r"\d", tokens[1]):
        return " ".join(tokens[:2]), " ".join(tokens[2:])
    return None


def separar_endereco(endereco: str) -> dict:
    """Divide o "Endereço" do Catalogo nas colunas de endereco do Censo Escolar.

    "JORGE PALMIRO MERCADO, 107 VILA TERESINHA. 02854-020 São Paulo - SP."
        -> logradouro JORGE PALMIRO MERCADO, numero 107, bairro VILA TERESINHA, CEP 02854020
    "OLGA FADEL ABARCA, S/N CEU ARICANDUVA. JARDIM SANTA TEREZINHA. 03572-020 São Paulo - SP."
        -> ..., numero S/N, complemento CEU ARICANDUVA, bairro JARDIM SANTA TEREZINHA

    O logradouro pode ter virgula ("R. X, QD. 2, 23 ..."): o corte e na
    ultima virgula seguida de numero. Com um so trecho depois do numero, ele
    e tratado como bairro; com dois, complemento e bairro.
    """
    texto = (endereco or "").strip()
    cep = ""
    fim = FIM_ENDERECO.search(texto)
    if fim:
        cep = fim.group(1).replace("-", "")
        texto = texto[:fim.start()]

    pedacos = texto.split(", ")
    corte = next((i for i in range(len(pedacos) - 1, 0, -1) if comeca_com_numero(pedacos[i])), 1)
    logradouro = ", ".join(pedacos[:corte])
    resto = ", ".join(pedacos[corte:]).strip().rstrip(".").strip()

    numero = ""
    achado = comeca_com_numero(resto)
    if achado:
        numero, resto = achado
    partes = [parte.strip() for parte in resto.split(". ")] if resto else []
    complemento, bairro = "", ""
    if len(partes) >= 2:
        complemento, bairro = partes[0], ". ".join(partes[1:])
    elif partes:
        bairro = partes[0]

    return {"DS_ENDERECO": logradouro.strip(), "NU_ENDERECO": numero, "DS_COMPLEMENTO": complemento.strip(),
            "NO_BAIRRO": bairro.strip(), "CO_CEP": cep}


def situacao_endereco(endereco: str, separado: dict) -> str:
    """ENDERECO_SEPARACAO: o que a separacao do endereco conseguiu, para os niveis 1 e 2."""
    if not (endereco or "").strip():
        return "sem_endereco"
    cep = bool(separado["CO_CEP"])
    numero = bool(etl.normalizar_numero(separado["NU_ENDERECO"]))
    if cep and numero:
        return "cep_e_numero"
    if cep:
        return "sem_numero"
    return "sem_cep" if numero else "sem_cep_e_numero"


def carregar_entrada(caminho: Path, codigos_uf: set) -> tuple:
    """Le a base juntada e devolve (escolas por UF, colunas, coordenadas do INEP).

    Separa o endereco de cada escola das UFs pedidas e marca
    ENDERECO_SEPARACAO. Escola sem CO_UF (so do Cadastro, ou sem UF no
    proprio Censo) usa a UF do Cadastro, para nao ficar de fora.

    coordenadas: CO_ENTIDADE -> (lat, lon, escolas_no_ponto), contando as
    escolas no mesmo ponto no Brasil todo, como carregar_coordenadas_inep do ETL.
    """
    if not caminho.exists():
        raise SystemExit("{} nao encontrado - rode antes: "
                         "inep_censo_escolar__juntar_cadastro_escolar.py".format(caminho))
    por_uf = {codigo: [] for codigo in codigos_uf}
    pontos = {}
    with open(caminho, encoding="utf-8", newline="") as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=";")
        colunas = list(leitor.fieldnames or [])
        repetidas = set(colunas) & set(COLUNAS_ENDERECO + COLUNAS_RASTREIO)
        if repetidas:
            raise SystemExit("a entrada ja tem as colunas {} - elas seriam sobrescritas".format(sorted(repetidas)))
        for linha in leitor:
            if not linha["CO_ENTIDADE"]:  # so no Cadastro
                linha["CO_ENTIDADE"] = linha["Código INEP"]
            # So no Cadastro, ou com a UF incompleta no proprio Censo (ex.: 43145833,
            # com CO_UF e sem SG_UF): completa pela UF do Cadastro
            if not linha["SG_UF"]:
                linha["SG_UF"] = linha["UF"]
            if not linha["CO_UF"]:
                linha["CO_UF"] = etl.UFS.get(linha["SG_UF"].lower(), "")
            lat, lon = linha["Latitude"].strip(), linha["Longitude"].strip()
            if lat and lon:
                pontos[linha["CO_ENTIDADE"]] = (round(float(lat), 6), round(float(lon), 6))
            if linha["CO_UF"] in por_uf:
                separado = separar_endereco(linha["Endereço"])
                linha.update(separado, ENDERECO_SEPARACAO=situacao_endereco(linha["Endereço"], separado))
                por_uf[linha["CO_UF"]].append(linha)
    no_ponto = collections.Counter(pontos.values())
    coordenadas = {codigo: (lat, lon, no_ponto[(lat, lon)]) for codigo, (lat, lon) in pontos.items()}
    return por_uf, colunas, coordenadas


def historico(linha: dict) -> str:
    """HISTORICO_PROCESSAMENTO: as etapas que o registro percorreu, em ordem, num texto curto."""
    etapas = ["1 juncao: " + linha[COLUNA_JUNCAO],
              "2 endereco: " + linha["ENDERECO_SEPARACAO"],
              "3 ponto_inep: " + ("sim ({} escola(s) no ponto)".format(linha["INEP_ESCOLAS_NO_PONTO"])
                                  if linha["INEP_LATITUDE"] != "" else "nao")]
    if linha["STATUS_CNEFE"] == "sem_correspondencia":
        cnefe = "sem_correspondencia ({})".format(linha["MOTIVO_GEOLOCALIZACAO"] or "-")
    else:
        cnefe = "nivel {} {} ({} candidato(s), similaridade do nome {})".format(
            linha["NIVEL_CASAMENTO"], linha["STATUS_CNEFE"], linha["N_CANDIDATOS"], linha["SIMILARIDADE_NOME"] or "-")
    if linha["ALERTAS_GEOLOCALIZACAO"]:
        cnefe += ", alertas " + linha["ALERTAS_GEOLOCALIZACAO"]
    etapas.append("4 cnefe: " + cnefe)
    coordenada = "{} ({})".format(linha["FONTE_COORDENADA"], linha["STATUS_GEOLOCALIZACAO"]) \
        if linha["FONTE_COORDENADA"] else "nenhuma (sem_correspondencia)"
    if linha["DIST_INEP_CNEFE_KM"] != "":
        coordenada += ", INEP x CNEFE {} km".format(linha["DIST_INEP_CNEFE_KM"])
    etapas.append("5 coordenada: " + coordenada)
    return " | ".join(etapas)


def montar_registros(linhas_saida: list, linhas_auditoria: list, linhas_cnefe: list, colunas_cnefe: list) -> list:
    """Junta a cada escola os campos da auditoria do ETL e a linha original do CNEFE casada.

    linhas_saida e linhas_auditoria vem de processar_uf na mesma ordem (uma
    por escola). A linha do CNEFE entra sempre que houve casamento, mesmo
    quando a coordenada final e a do INEP.
    """
    cnefe_por_codigo = {
        linha["COD_UNICO_ENDERECO"]: {"CNEFE_" + coluna: linha[coluna] for coluna in colunas_cnefe}
        for linha in linhas_cnefe
    }
    registros = []
    for saida, auditoria in zip(linhas_saida, linhas_auditoria):
        assert saida["CO_ENTIDADE"] == auditoria["CO_ENTIDADE"]
        registro = dict(saida, **{coluna: auditoria[coluna] for coluna in COLUNAS_DA_AUDITORIA})
        cnefe = cnefe_por_codigo.get(saida["CNEFE_COD_UNICO_ENDERECO"])
        registro["CNEFE_JUNTADO"] = "sim" if cnefe else "nao"
        if cnefe:
            registro.update(cnefe)
        registro["HISTORICO_PROCESSAMENTO"] = historico(registro)
        registros.append(registro)
    return registros


def principal() -> None:
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument("ufs", nargs="*", choices=list(etl.UFS) + [[]], type=str.lower,
                            help="siglas das UFs a processar (padrao: as que ja tem CNEFE baixado)")
    analisador.add_argument("--entrada", type=Path, default=ENTRADA, help="padrao: {}".format(ENTRADA))
    analisador.add_argument("--saida", type=Path, default=SAIDA, help="padrao: {}".format(SAIDA))
    argumentos = analisador.parse_args()

    ufs_pedidas = argumentos.ufs or etl.ufs_com_cnefe_baixado()
    if not ufs_pedidas:
        raise SystemExit("nenhuma UF com CNEFE baixado em {}".format(etl.DIR_CNEFE))
    ufs_processadas = {uf.upper() for uf in ufs_pedidas}

    etl.ANO_CENSO_ESCOLAR = ANO  # so aparece nas mensagens de processar_uf
    print("Censo Escolar {} + Cadastro Escolar: {}".format(ANO, argumentos.entrada))
    por_uf, colunas, coordenadas = carregar_entrada(argumentos.entrada, {etl.UFS[uf] for uf in ufs_pedidas})
    print("    {} escolas com ponto do INEP (Brasil)".format(len(coordenadas)))

    # Grava UF por UF num arquivo temporario (com 27 UFs, juntar todos os
    # registros na memoria antes de gravar fica pesado). As linhas de UFs
    # ja presentes na saida e nao reprocessadas agora sao mantidas, como no ETL.
    temporario = argumentos.saida.with_suffix(argumentos.saida.suffix + ".tmp")
    arquivo, escritor = None, None
    contagens_totais, rastreio = collections.Counter(), collections.defaultdict(collections.Counter)
    gravadas = 0
    for uf in ufs_pedidas:
        escolas = por_uf.pop(etl.UFS[uf])
        linhas_saida, linhas_auditoria, _, linhas_cnefe, colunas_cnefe, contagens = etl.processar_uf(
            uf, escolas, coordenadas)
        registros = montar_registros(linhas_saida, linhas_auditoria, linhas_cnefe, colunas_cnefe)
        del escolas, linhas_saida, linhas_auditoria, linhas_cnefe
        if escritor is None:
            # Colunas do CNEFE ja gravadas pelo ETL com o mesmo nome (mesmo valor) nao se repetem
            colunas_saida = colunas + COLUNAS_ENDERECO + COLUNAS_RASTREIO + etl.COLUNAS_NOVAS + COLUNAS_DA_AUDITORIA
            colunas_saida += [c for c in ("CNEFE_" + c for c in colunas_cnefe) if c not in colunas_saida]
            argumentos.saida.parent.mkdir(parents=True, exist_ok=True)
            arquivo = open(temporario, "w", encoding="utf-8", newline="")
            escritor = csv.DictWriter(arquivo, fieldnames=colunas_saida, delimiter=";", restval="",
                                      extrasaction="ignore")
            escritor.writeheader()
        escritor.writerows(registros)
        gravadas += len(registros)
        contagens_totais.update(contagens)
        for coluna in (COLUNA_JUNCAO, "ENDERECO_SEPARACAO", "CNEFE_JUNTADO"):
            rastreio[coluna].update(r[coluna] for r in registros)

    mantidas = 0
    if argumentos.saida.exists():
        with open(argumentos.saida, encoding="utf-8", newline="") as anterior:
            for linha in csv.DictReader(anterior, delimiter=";"):
                if linha["SG_UF"] not in ufs_processadas:
                    escritor.writerow(linha)
                    mantidas += 1
    arquivo.close()
    temporario.replace(argumentos.saida)
    print("{}: {} linhas novas, {} mantidas de outras UFs".format(argumentos.saida, gravadas, mantidas))

    total = sum(contagens_totais.values()) or 1
    print("\nResumo geral ({} UF(s), {} escolas)".format(len(ufs_pedidas), total))
    for status in etl.STATUS:
        print("  {:22s} {:6d}  ({:.1f}%)".format(status, contagens_totais[status], 100 * contagens_totais[status] / total))
    for coluna, contagem in rastreio.items():
        print("  {}: {}".format(coluna, dict(contagem.most_common())))


if __name__ == "__main__":
    sys.exit(principal())
