#!/usr/bin/env python3
"""Exploracao basica dos microdados do Censo Escolar (INEP) pela linha de comando.

Le os CSVs direto do ZIP baixado por inep_censo_escolar__baixar_dados.py, sem
precisar extrair (o de 2025 tem 537 MB). A tabela e indicada por um nome
curto: escola, matricula, docente, turma, gestor, curso (basta o comeco do
nome; "tabelas" lista as que existem). Sem tabela, usa "escola".

Os comandos que olham a tabela inteira (tail, amostra, contar, resumo,
filtrar) leem o CSV em blocos, para nao carregar centenas de MB na memoria.
Os valores sao lidos como texto, para que codigos como CO_ENTIDADE e as
categorias TP_* aparecam como estao no arquivo (1, e nao 1.0).

Uso (a partir da raiz do projeto):
    PY=".venv/bin/python scripts/utils/explorardados.py"
    $PY tabelas
    $PY colunas escola --filtro INTERNET --descricao
    $PY head escola -n 3 --colunas CO_ENTIDADE,NO_ENTIDADE,SG_UF
    $PY tail matricula -n 2 --sem-vazias
    $PY amostra escola -n 5 --semente 42
    $PY contar escola TP_DEPENDENCIA
    $PY contar escola SG_UF TP_LOCALIZACAO --top 10
    $PY contar escola TP_DEPENDENCIA --onde "SG_UF == 'AM'"
    $PY resumo matricula --colunas QT_MAT_BAS,QT_MAT_INF
    $PY filtrar escola --onde "SG_UF == 'AM' and TP_DEPENDENCIA == '3'" \\
        --colunas CO_ENTIDADE,NO_ENTIDADE,NO_MUNICIPIO --saida /tmp/am_municipais.csv
    $PY dicionario TP_DEPENDENCIA
    $PY dicionario internet --tabela escola

Outro ano: --ano 2024. Outro CSV qualquer: --arquivo caminho.csv (com
--sep se nao for ";"; a codificacao, utf-8 ou latin-1, e detectada).

Em --onde os valores sao texto: compare com aspas (TP_DEPENDENCIA == '3').
Para comparar numeros, converta: "QT_MAT_BAS.astype('float') > 1000" (o
script ja faz isso sozinho para colunas citadas com > < >= <=).
"""

import argparse
import io
import random
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent.parent
PASTA_ZIPS = RAIZ / "data" / "inep_censo_escolar" / "zipfiles"
ANO_PADRAO = "2025"
TABELA_PADRAO = "escola"
SEP_PADRAO = ";"
ENCODING_ZIP = "latin-1"  # os CSVs do INEP vem em latin-1

# Nomes curtos que mudam entre anos: ate 2024 a tabela de escolas era um
# CSV unico "microdados_ed_basica_<ano>.csv".
APELIDOS = {"escola": ["microdados_ed_basica"], "curso": ["suplemento_cursos_tecnicos"]}
BLOCO = 50_000  # linhas por bloco nos comandos que leem a tabela inteira
MAX_DISTINTOS = 1_000  # acima disso o resumo mostra so "> 1000"

NS_XLSX = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


# ---------------------------------------------------------------- fontes

class Fonte:
    """Um CSV a explorar: dentro do ZIP do Censo ou solto no disco."""

    def __init__(self, rotulo, abrir, sep, encoding, zip_=None):
        self.rotulo = rotulo  # texto mostrado no cabecalho da saida
        self._abrir = abrir  # funcao sem argumentos que devolve um arquivo binario
        self.sep = sep
        self.encoding = encoding
        self.zip = zip_  # ZipFile do Censo, para achar o dicionario

    def ler(self, **kwargs):
        """pd.read_csv sobre a fonte, sempre como texto."""
        opcoes = dict(sep=self.sep, encoding=self.encoding, dtype=str, low_memory=False)
        opcoes.update(kwargs)
        return pd.read_csv(self._abrir(), **opcoes)

    def blocos(self, usecols=None):
        """Itera a tabela em blocos de BLOCO linhas."""
        return self.ler(usecols=usecols, chunksize=BLOCO)

    def colunas(self):
        """Nomes das colunas, lendo so o cabecalho."""
        return list(self.ler(nrows=0).columns)


def chave_tabela(nome):
    """'.../Tabela_Gestor_Escolar_2025_v2.csv' -> 'gestor_escolar'."""
    chave = Path(nome).stem.lower()
    chave = re.sub(r"^tabela_", "", chave)
    chave = re.sub(r"_v\d+$", "", chave)
    chave = re.sub(r"_?\d{4}$", "", chave)
    return chave


def adivinhar_encoding(caminho):
    """utf-8 se o primeiro MB decodifica como utf-8; senao latin-1.

    Os CSVs gerados pelo projeto sao utf-8; os do INEP, latin-1.
    """
    with open(caminho, "rb") as arquivo:
        inicio = arquivo.read(1024 * 1024)
    try:
        inicio.decode("utf-8")
    except UnicodeDecodeError as erro:
        if erro.start < len(inicio) - 4:  # nao foi so um caractere cortado no fim
            return "latin-1"
    return "utf-8"


def caminho_zip(ano):
    """ZIP do ano em data/inep_censo_escolar/zipfiles/."""
    caminho = PASTA_ZIPS / "microdados_censo_escolar_{}.zip".format(ano)
    if not caminho.exists():
        sair(
            "Nao achei {}.\nBaixe com: .venv/bin/python "
            "scripts/commands/inep_censo_escolar__baixar_dados.py {}".format(caminho, ano)
        )
    return caminho


def csvs_do_zip(arquivo_zip):
    """{chave: nome dentro do ZIP} para os CSVs da pasta dados/."""
    return {
        chave_tabela(nome): nome
        for nome in arquivo_zip.namelist()
        if nome.lower().endswith(".csv") and "/dados/" in nome.lower()
    }


def escolher_tabela(tabelas, pedido):
    """Acha a tabela pelo nome curto (comeco ou trecho do nome)."""
    pedido = pedido.lower()
    if pedido in tabelas:
        return pedido
    for apelido in APELIDOS.get(pedido, []):
        if apelido in tabelas:
            return apelido
    candidatas = [c for c in tabelas if c.startswith(pedido)] or [c for c in tabelas if pedido in c]
    if len(candidatas) == 1:
        return candidatas[0]
    if len(tabelas) == 1:
        return next(iter(tabelas))  # anos antigos: um CSV so no ZIP
    sair(
        "Tabela '{}' {}. Tabelas disponiveis: {}".format(
            pedido, "ambigua" if candidatas else "nao encontrada", ", ".join(sorted(tabelas))
        )
    )


def abrir_fonte(args, precisa_tabela=True):
    """Monta a Fonte a partir de --arquivo ou de --ano + tabela."""
    if args.arquivo:
        caminho = Path(args.arquivo)
        if not caminho.exists():
            sair("Arquivo nao encontrado: {}".format(caminho))
        encoding = args.encoding or adivinhar_encoding(caminho)
        return Fonte(str(caminho), lambda: open(caminho, "rb"), args.sep, encoding)

    arquivo_zip = zipfile.ZipFile(caminho_zip(args.ano))
    if not precisa_tabela:
        return Fonte(arquivo_zip.filename, None, args.sep, args.encoding or ENCODING_ZIP, arquivo_zip)
    tabelas = csvs_do_zip(arquivo_zip)
    chave = escolher_tabela(tabelas, getattr(args, "tabela", None) or TABELA_PADRAO)
    nome = tabelas[chave]
    return Fonte(
        "{} ({})".format(chave, Path(nome).name),
        lambda: arquivo_zip.open(nome),
        args.sep,
        args.encoding or ENCODING_ZIP,
        arquivo_zip,
    )


# ------------------------------------------------------------ dicionario

def ler_planilhas_xlsx(conteudo):
    """{nome da aba: [linhas]} de um .xlsx, so com a biblioteca padrao.

    Cada linha e um dict {letra da coluna: texto}. Evita depender do openpyxl,
    que nao esta no ambiente do projeto.
    """
    xlsx = zipfile.ZipFile(io.BytesIO(conteudo))
    m = "{%s}" % NS_XLSX["m"]
    compartilhados = []
    if "xl/sharedStrings.xml" in xlsx.namelist():
        raiz = ET.fromstring(xlsx.read("xl/sharedStrings.xml"))
        compartilhados = ["".join(t.text or "" for t in si.iter(m + "t")) for si in raiz.findall("m:si", NS_XLSX)]

    # nome da aba -> arquivo da planilha, via workbook.xml + rels
    rels = ET.fromstring(xlsx.read("xl/_rels/workbook.xml.rels"))
    alvo = {r.get("Id"): r.get("Target") for r in rels}
    livro = ET.fromstring(xlsx.read("xl/workbook.xml"))
    id_rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

    planilhas = {}
    for aba in livro.find("m:sheets", NS_XLSX):
        destino = alvo[aba.get(id_rel)].lstrip("/")
        destino = destino if destino.startswith("xl/") else "xl/" + destino
        linhas = []
        for linha in ET.fromstring(xlsx.read(destino)).iter(m + "row"):
            valores = {}
            for celula in linha.findall("m:c", NS_XLSX):
                letra = re.match(r"[A-Z]+", celula.get("r")).group()
                v = celula.find("m:v", NS_XLSX)
                if v is not None:
                    texto = compartilhados[int(v.text)] if celula.get("t") == "s" else v.text
                else:
                    t = celula.find("m:is/m:t", NS_XLSX)
                    texto = t.text if t is not None else None
                if texto is not None and texto.strip():
                    valores[letra] = texto.strip()
            linhas.append(valores)
        planilhas[aba.get("name").strip()] = linhas
    return planilhas


def ler_dicionario(arquivo_zip):
    """Le o dicionario de dados que vem no ZIP do Censo.

    Devolve uma lista de dicts com aba, variavel, descricao, tipo, tamanho e
    categorias. As colunas sao achadas pelo cabecalho ("Nome da Variavel"...),
    e nao por posicao fixa, para aguentar pequenas mudancas entre anos.
    """
    nomes = [n for n in arquivo_zip.namelist() if n.lower().endswith(".xlsx") and "dicion" in n.lower()]
    if not nomes:
        sair("Este ZIP nao traz um dicionario de dados (.xlsx).")
    variaveis = []
    for aba, linhas in ler_planilhas_xlsx(arquivo_zip.read(nomes[0])).items():
        colunas = None
        for linha in linhas:
            if colunas is None:
                textos = {letra: texto.lower() for letra, texto in linha.items()}
                achar = lambda trecho: next((l for l, t in textos.items() if trecho in t), None)  # noqa: E731
                if achar("nome da vari"):
                    colunas = {
                        "variavel": achar("nome da vari"),
                        "descricao": achar("descri"),
                        "tipo": achar("tipo"),
                        "tamanho": achar("tam"),
                        "categorias": achar("categoria"),
                    }
                continue
            nome = linha.get(colunas["variavel"], "")
            if not re.fullmatch(r"[A-Z][A-Z0-9_]+", nome):
                continue  # linhas de titulo, notas, anos da coleta
            item = {chave: linha.get(letra, "") if letra else "" for chave, letra in colunas.items()}
            item["aba"] = aba
            variaveis.append(item)
    return variaveis


def rotulos(categorias):
    """'1 - Federal\\n2 - Estadual' -> {'1': 'Federal', '2': 'Estadual'}."""
    resultado = {}
    for linha in (categorias or "").splitlines():
        achado = re.match(r"\s*(-?\w+)\s*[-–=:]\s*(.+)", linha)
        if achado:
            resultado[achado.group(1)] = achado.group(2).strip()
    return resultado


def dicionario_da_fonte(fonte):
    """{variavel: item do dicionario} ou {} se nao houver dicionario."""
    if fonte.zip is None:
        return {}
    try:
        return {item["variavel"]: item for item in ler_dicionario(fonte.zip)}
    except SystemExit:
        return {}


# ------------------------------------------------------------- utilidades

def sair(mensagem):
    """Mostra o erro e encerra com codigo 1."""
    print("erro: " + mensagem, file=sys.stderr)
    sys.exit(1)


def lista_colunas(texto):
    """'A, B,C' -> ['A', 'B', 'C'] (ou None)."""
    if not texto:
        return None
    return [c.strip() for c in texto.split(",") if c.strip()]


def conferir_colunas(fonte, pedidas):
    """Erro amigavel se alguma coluna pedida nao existe na tabela."""
    if not pedidas:
        return
    existentes = set(fonte.colunas())
    faltando = [c for c in pedidas if c not in existentes]
    if faltando:
        parecidas = [c for c in existentes if any(f.lower() in c.lower() for f in faltando)]
        dica = " Parecidas: {}".format(", ".join(sorted(parecidas)[:15])) if parecidas else ""
        sair("Colunas inexistentes: {}.{}".format(", ".join(faltando), dica))


def configurar_pandas():
    """Saida do pandas na largura do terminal, sem cortar linhas."""
    largura = shutil.get_terminal_size((160, 40)).columns
    pd.set_option("display.width", largura)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.max_colwidth", 60)


def mostrar(df, args, titulo):
    """Imprime linhas: na vertical (uma coluna por linha) se forem muitas colunas."""
    if getattr(args, "sem_vazias", False):
        df = df.dropna(axis=1, how="all")
    print("== {} ==".format(titulo))
    if df.empty:
        print("(nenhuma linha)")
        return
    vertical = not getattr(args, "horizontal", False) and df.shape[1] > 8
    print((df.T if vertical else df).fillna("").to_string())
    print("({} linha(s) x {} coluna(s){})".format(df.shape[0], df.shape[1], ", na vertical" if vertical else ""))


def preparar_consulta(expressao, colunas):
    """Converte para numero as colunas comparadas com > < >= <= na expressao.

    Como tudo e lido como texto, "QT_MAT_BAS > 100" compararia textos. Aqui
    a coluna vira float antes do query; == e != continuam como texto.
    """
    numericas = {c for c in colunas if re.search(r"\b{}\b\s*(<=|>=|<|>)".format(re.escape(c)), expressao)}
    numericas |= {c for c in colunas if re.search(r"(<=|>=|<|>)\s*\b{}\b".format(re.escape(c)), expressao)}
    return numericas


def aplicar_filtro(bloco, expressao, numericas):
    """Aplica --onde a um bloco, com as colunas numericas convertidas."""
    if not expressao:
        return bloco
    trabalho = bloco.copy()
    for coluna in numericas:
        trabalho[coluna] = pd.to_numeric(trabalho[coluna], errors="coerce")
    try:
        mascara = trabalho.eval(expressao)
    except Exception as erro:  # noqa: BLE001 - mensagem do pandas e o melhor diagnostico
        sair("expressao --onde invalida: {}\n  {}".format(expressao, erro))
        raise  # inalcancavel; deixa claro que mascara sempre existe abaixo
    # "SG_UF = 'AM'" (um "=" so) e uma atribuicao para o pandas: devolve a
    # tabela inteira em vez de verdadeiro/falso por linha.
    if not isinstance(mascara, pd.Series) or len(mascara) != len(bloco):
        sair("--onde precisa ser uma condicao (use == para comparar): {}".format(expressao))
    return bloco[mascara.fillna(False).astype(bool)]


def colunas_da_expressao(expressao, colunas):
    """Colunas citadas em --onde (para ler so o necessario)."""
    if not expressao:
        return []
    return [c for c in colunas if re.search(r"\b{}\b".format(re.escape(c)), expressao)]


# -------------------------------------------------------------- comandos

def cmd_tabelas(args):
    """Lista os CSVs do ZIP, com o nome curto e o tamanho."""
    fonte = abrir_fonte(args, precisa_tabela=False)
    if fonte.zip is None:
        sair("'tabelas' so funciona com o ZIP do Censo (sem --arquivo).")
    print("== {} ==".format(fonte.rotulo))
    for chave, nome in sorted(csvs_do_zip(fonte.zip).items()):
        tamanho = fonte.zip.getinfo(nome).file_size / (1024 * 1024)
        print("  {:<16} {:>8.1f} MB  {}".format(chave, tamanho, nome))


def cmd_colunas(args):
    """Lista as colunas, com indice e (opcional) a descricao do dicionario."""
    fonte = abrir_fonte(args)
    colunas = fonte.colunas()
    dicionario = dicionario_da_fonte(fonte) if args.descricao else {}
    filtro = (args.filtro or "").lower()
    print("== {}: {} colunas ==".format(fonte.rotulo, len(colunas)))
    mostradas = 0
    for indice, coluna in enumerate(colunas, 1):
        descricao = dicionario.get(coluna, {}).get("descricao", "")
        if filtro and filtro not in coluna.lower() and filtro not in descricao.lower():
            continue
        mostradas += 1
        print("  {:>4}  {:<40} {}".format(indice, coluna, descricao).rstrip())
    if filtro:
        print("({} coluna(s) com '{}')".format(mostradas, args.filtro))


def cmd_head(args):
    """Primeiras N linhas."""
    fonte = abrir_fonte(args)
    colunas = lista_colunas(args.colunas)
    conferir_colunas(fonte, colunas)
    df = fonte.ler(nrows=args.n, usecols=colunas)
    mostrar(df[colunas] if colunas else df, args, "{}: primeiras {}".format(fonte.rotulo, args.n))


def cmd_tail(args):
    """Ultimas N linhas (le a tabela toda em blocos)."""
    fonte = abrir_fonte(args)
    colunas = lista_colunas(args.colunas)
    conferir_colunas(fonte, colunas)
    ultimas = None
    total = 0
    for bloco in fonte.blocos(colunas):
        total += len(bloco)
        ultimas = bloco if ultimas is None else pd.concat([ultimas, bloco]).tail(args.n)
    df = ultimas.tail(args.n) if ultimas is not None else pd.DataFrame()
    mostrar(df[colunas] if colunas else df, args, "{}: ultimas {} de {}".format(fonte.rotulo, args.n, mil(total)))


def cmd_amostra(args):
    """N linhas sorteadas de forma uniforme entre todas (le em blocos)."""
    fonte = abrir_fonte(args)
    colunas = lista_colunas(args.colunas)
    conferir_colunas(fonte, colunas)
    sorteio = random.Random(args.semente)
    guardadas = None
    total = 0
    # Cada linha recebe um numero aleatorio; ficam as N de menor numero.
    # Isso equivale a sortear N linhas sem reposicao entre todas.
    for bloco in fonte.blocos(colunas):
        total += len(bloco)
        bloco = bloco.assign(_sorteio=[sorteio.random() for _ in range(len(bloco))])
        juntas = bloco if guardadas is None else pd.concat([guardadas, bloco])
        guardadas = juntas.nsmallest(args.n, "_sorteio")
    df = guardadas.sort_index().drop(columns="_sorteio") if guardadas is not None else pd.DataFrame()
    titulo = "{}: amostra de {} entre {}{}".format(
        fonte.rotulo, len(df), mil(total), "" if args.semente is None else " (semente {})".format(args.semente)
    )
    mostrar(df[colunas] if colunas else df, args, titulo)


def cmd_contar(args):
    """Frequencia dos valores de uma ou mais colunas (tabela cruzada se forem varias)."""
    if args.arquivo:  # sem ZIP nao ha tabela: o primeiro nome ja e uma coluna
        args.coluna = [args.tabela] + args.coluna
    if not args.coluna:
        sair("informe ao menos uma coluna, ex.: contar escola TP_DEPENDENCIA")
    fonte = abrir_fonte(args)
    todas = fonte.colunas()
    conferir_colunas(fonte, args.coluna)
    extras = colunas_da_expressao(args.onde, todas)
    numericas = preparar_consulta(args.onde or "", extras)
    contagem = None
    total = 0
    for bloco in fonte.blocos(sorted(set(args.coluna) | set(extras))):
        bloco = aplicar_filtro(bloco, args.onde, numericas)
        total += len(bloco)
        parcial = bloco[args.coluna].fillna("(vazio)").value_counts()
        contagem = parcial if contagem is None else contagem.add(parcial, fill_value=0)

    print("== {}: {} ==".format(fonte.rotulo, " x ".join(args.coluna)))
    if args.onde:
        print("filtro: {}".format(args.onde))
    if contagem is None or contagem.empty:
        print("(nenhuma linha)")
        return
    contagem = contagem.astype(int).sort_values(ascending=False)
    distintos = len(contagem)
    tabela = contagem.rename("linhas").to_frame()
    tabela["%"] = (100 * tabela["linhas"] / total).round(2)
    if len(args.coluna) == 1:
        tabela.index = tabela.index.get_level_values(0)
        mapa = rotulos(dicionario_da_fonte(fonte).get(args.coluna[0], {}).get("categorias"))
        if mapa:
            tabela.insert(0, "significado", [mapa.get(str(v), "") for v in tabela.index])
    if args.ordenar_valor:
        tabela = tabela.sort_index()
    if args.top and distintos > args.top:
        tabela = tabela.head(args.top)
    print(tabela.to_string())
    print("({} linha(s); {} valor(es) distinto(s){})".format(
        mil(total), mil(distintos), ", mostrando {}".format(args.top) if args.top and distintos > args.top else ""
    ))


def cmd_resumo(args):
    """Por coluna: preenchimento, distintos, se e numerica, min/max/media, exemplo."""
    fonte = abrir_fonte(args)
    colunas = lista_colunas(args.colunas)
    conferir_colunas(fonte, colunas)
    inicio = time.time()
    estado = {}
    total = 0
    for bloco in fonte.blocos(colunas):
        total += len(bloco)
        for coluna in bloco.columns:
            serie = bloco[coluna]
            e = estado.setdefault(coluna, {
                "nulos": 0, "distintos": set(), "estourou": False, "numerica": True,
                "min": None, "max": None, "soma": 0.0, "n": 0, "exemplo": None,
            })
            e["nulos"] += int(serie.isna().sum())
            preenchida = serie.dropna()
            if preenchida.empty:
                continue
            if e["exemplo"] is None:
                e["exemplo"] = preenchida.iloc[0]
            if not e["estourou"]:
                e["distintos"].update(preenchida.unique())
                if len(e["distintos"]) > MAX_DISTINTOS:
                    e["estourou"], e["distintos"] = True, set()
            if e["numerica"]:
                numeros = pd.to_numeric(preenchida, errors="coerce")
                if numeros.isna().any():
                    e["numerica"] = False
                else:
                    e["min"] = numeros.min() if e["min"] is None else min(e["min"], numeros.min())
                    e["max"] = numeros.max() if e["max"] is None else max(e["max"], numeros.max())
                    e["soma"] += float(numeros.sum())
                    e["n"] += len(numeros)

    linhas = []
    for coluna, e in estado.items():
        numerica = e["numerica"] and e["n"] > 0
        linhas.append({
            "coluna": coluna,
            "tipo": "num" if numerica else "texto",
            "preenchidas": total - e["nulos"],
            "% vazias": round(100 * e["nulos"] / total, 1) if total else 0,
            "distintos": "> {}".format(MAX_DISTINTOS) if e["estourou"] else len(e["distintos"]),
            "min": fmt_num(e["min"]) if numerica else "",
            "max": fmt_num(e["max"]) if numerica else "",
            "media": fmt_num(e["soma"] / e["n"]) if numerica else "",
            "exemplo": (e["exemplo"] or "")[:40],
        })
    print("== {}: resumo de {} linhas x {} colunas ({:.0f}s) ==".format(
        fonte.rotulo, mil(total), len(linhas), time.time() - inicio
    ))
    print(pd.DataFrame(linhas).set_index("coluna").to_string())


def fmt_num(valor):
    """Numero sem separador de milhar (codigos e anos ficam legiveis), virgula decimal."""
    if valor is None:
        return ""
    if float(valor).is_integer():
        return "{:.0f}".format(valor)
    return "{:.2f}".format(valor).replace(".", ",")


def mil(numero):
    """Contagem com ponto de milhar: 214192 -> '214.192'."""
    return "{:,}".format(int(numero)).replace(",", ".")


def cmd_filtrar(args):
    """Linhas que atendem --onde; mostra as primeiras N e pode gravar todas em CSV."""
    fonte = abrir_fonte(args)
    colunas = lista_colunas(args.colunas)
    conferir_colunas(fonte, colunas)
    todas = fonte.colunas()
    extras = colunas_da_expressao(args.onde, todas)
    if not extras:
        sair("--onde nao cita nenhuma coluna da tabela: {}".format(args.onde))
    numericas = preparar_consulta(args.onde, extras)
    leitura = sorted(set(colunas) | set(extras)) if colunas else None

    primeiras = []
    total = 0
    saida = None
    if args.saida:
        saida = open(args.saida, "w", encoding="utf-8", newline="")
    try:
        for bloco in fonte.blocos(leitura):
            achadas = aplicar_filtro(bloco, args.onde, numericas)
            if colunas:
                achadas = achadas[colunas]
            if saida and not achadas.empty:
                achadas.to_csv(saida, sep=";", index=False, header=total == 0)
            total += len(achadas)
            if sum(len(p) for p in primeiras) < args.n:
                primeiras.append(achadas)
    finally:
        if saida:
            saida.close()
    df = pd.concat(primeiras).head(args.n) if primeiras else pd.DataFrame()
    mostrar(df, args, "{}: {} -> {} linha(s), mostrando ate {}".format(fonte.rotulo, args.onde, mil(total), args.n))
    if args.saida:
        print("Gravado em {} (UTF-8, separador ';')".format(args.saida))


def cmd_dicionario(args):
    """Procura variaveis no dicionario de dados (nome ou descricao)."""
    fonte = abrir_fonte(args, precisa_tabela=False)
    if fonte.zip is None:
        sair("'dicionario' so funciona com o ZIP do Censo (sem --arquivo).")
    variaveis = ler_dicionario(fonte.zip)
    termo = (args.termo or "").lower()
    aba = (args.tabela or "").lower()
    achadas = [
        v for v in variaveis
        if (not aba or aba in v["aba"].lower())
        and (not termo or termo in v["variavel"].lower() or termo in v["descricao"].lower())
    ]
    exatas = [v for v in achadas if v["variavel"].lower() == termo]
    if exatas:
        # nome exato: mostra so ele, uma vez por definicao diferente (a mesma
        # variavel costuma se repetir igual em todas as abas)
        unicas = {}
        for v in exatas:
            chave = (v["descricao"], v["tipo"], v["tamanho"], v["categorias"])
            if chave in unicas:
                unicas[chave]["aba"] += ", " + v["aba"]
            else:
                unicas[chave] = dict(v)
        achadas = list(unicas.values())
    print("== dicionario {}: {} variavel(is) ==".format(args.ano, len(achadas)))
    detalhar = len(achadas) <= args.detalhar
    for v in achadas:
        if detalhar:
            print("\n{}  {} {}  [{}]".format(v["variavel"], v["tipo"], v["tamanho"], v["aba"]).rstrip())
            print("  " + v["descricao"])
            for linha in (v["categorias"] or "").splitlines():
                print("    " + linha.strip())
        else:
            print("  {:<40} {:<22} {}".format(v["variavel"], v["aba"][:22], v["descricao"][:90]))
    if not detalhar and achadas:
        print("(muitos resultados: so a lista. Refine o termo para ver as categorias.)")


# ----------------------------------------------------------- linha de comando

def montar_argumentos():
    """Define os subcomandos e as opcoes comuns."""
    comum = argparse.ArgumentParser(add_help=False)
    origem = comum.add_argument_group("origem dos dados")
    origem.add_argument("--ano", default=ANO_PADRAO, help="ano do Censo (padrao: %(default)s)")
    origem.add_argument("--arquivo", help="explorar este CSV em vez do ZIP do Censo")
    origem.add_argument("--sep", default=SEP_PADRAO, help="separador do CSV (padrao: '%(default)s')")
    origem.add_argument("--encoding", help="codificacao do CSV (padrao: latin-1 no ZIP; com --arquivo, detecta utf-8/latin-1)")

    linhas = argparse.ArgumentParser(add_help=False)
    linhas.add_argument("tabela", nargs="?", help="escola, matricula, docente, turma, gestor, curso")
    linhas.add_argument("-n", type=int, default=5, help="quantas linhas (padrao: %(default)s)")
    linhas.add_argument("--colunas", help="so estas colunas, separadas por virgula")
    linhas.add_argument("--sem-vazias", action="store_true", help="esconde colunas vazias nas linhas mostradas")
    linhas.add_argument("--horizontal", action="store_true", help="nao virar a tabela mesmo com muitas colunas")

    analisador = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Exemplos: veja o inicio do arquivo (" + Path(__file__).name + ").",
    )
    sub = analisador.add_subparsers(dest="comando", required=True, metavar="comando")

    p = sub.add_parser("tabelas", parents=[comum], help="lista as tabelas (CSVs) do ZIP")
    p.set_defaults(funcao=cmd_tabelas)

    p = sub.add_parser("colunas", parents=[comum], help="lista as colunas de uma tabela")
    p.add_argument("tabela", nargs="?")
    p.add_argument("--filtro", help="so colunas cujo nome (ou descricao) contem este texto")
    p.add_argument("--descricao", action="store_true", help="mostra a descricao do dicionario")
    p.set_defaults(funcao=cmd_colunas)

    for nome, funcao, ajuda in [
        ("head", cmd_head, "primeiras linhas"),
        ("tail", cmd_tail, "ultimas linhas"),
        ("amostra", cmd_amostra, "linhas sorteadas"),
    ]:
        p = sub.add_parser(nome, parents=[comum, linhas], help=ajuda)
        p.set_defaults(funcao=funcao)
        if nome == "amostra":
            p.add_argument("--semente", type=int, help="semente do sorteio (para repetir a mesma amostra)")

    p = sub.add_parser("contar", parents=[comum], help="frequencia dos valores de uma ou mais colunas")
    p.add_argument("tabela")
    p.add_argument("coluna", nargs="*", help="uma coluna, ou varias para uma tabela cruzada")
    p.add_argument("--top", type=int, default=30, help="mostrar so os N mais frequentes (0 = todos; padrao: %(default)s)")
    p.add_argument("--onde", help="filtro antes de contar, ex.: \"SG_UF == 'AM'\"")
    p.add_argument("--ordenar-valor", action="store_true", help="ordenar pelo valor, e nao pela frequencia")
    p.set_defaults(funcao=cmd_contar)

    p = sub.add_parser("resumo", parents=[comum], help="preenchimento, distintos, min/max/media por coluna")
    p.add_argument("tabela", nargs="?")
    p.add_argument("--colunas", help="so estas colunas (a tabela de escolas inteira leva mais tempo)")
    p.set_defaults(funcao=cmd_resumo)

    p = sub.add_parser("filtrar", parents=[comum, linhas], help="linhas que atendem a uma condicao")
    p.add_argument("--onde", required=True, help="condicao no formato do pandas.eval")
    p.add_argument("--saida", help="grava todas as linhas achadas neste CSV")
    p.set_defaults(funcao=cmd_filtrar)

    p = sub.add_parser("dicionario", parents=[comum], help="procura variaveis no dicionario de dados do INEP")
    p.add_argument("termo", nargs="?", help="trecho do nome ou da descricao (sem termo: lista tudo)")
    p.add_argument("--tabela", help="so a aba desta tabela (escola, matricula...)")
    p.add_argument("--detalhar", type=int, default=10, help="mostra categorias se houver ate N resultados (padrao: %(default)s)")
    p.set_defaults(funcao=cmd_dicionario)

    return analisador


def principal():
    """Le a linha de comando e executa o subcomando."""
    args = montar_argumentos().parse_args()
    configurar_pandas()
    try:
        args.funcao(args)
    except BrokenPipeError:  # saida cortada por "| head"
        sys.stderr.close()


if __name__ == "__main__":
    principal()
