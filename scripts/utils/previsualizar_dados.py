#!/usr/bin/env python3
"""Pré-visualização visual interativa de conjuntos de dados no navegador.

Lê apenas o esquema e um número limitado de linhas (ou amostra uniforme) de
CSV/TSV, ZIP (CSV único, Censo Escolar multi-tabela + dicionário .xlsx, ou
Shapefile compactado), arquivos geoespaciais (.gpkg, .geojson, .shp, .fgb, .kml),
planilhas Excel (.xlsx) e JSON/JSONL. Gera um HTML auto-contido e offline em
temp/ e abre no navegador padrão.

Exemplos (a partir da raiz do projeto):
    PY=".venv/bin/python scripts/utils/previsualizar_dados.py"
    $PY data/auditoria/escolas_inep_x_cnefe_2024.csv -n 30
    $PY data/ibge_cnefe/zipfiles/13_AM.zip -n 20
    $PY data/inep_censo_escolar/zipfiles/microdados_censo_escolar_2025.zip --listar
    $PY data/inep_censo_escolar/zipfiles/microdados_censo_escolar_2025.zip --tabela escola -n 30
    $PY data/ibge_malha_municipal/zipfiles/BR_UF_2024.zip -n 10
"""

import argparse
import csv
import heapq
import io
import itertools
import json
import random
import re
import statistics
import sys
import time
import webbrowser
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent.parent
PASTA_TEMP = RAIZ / "temp"
BLOCO = 50_000
APELIDOS_TABELA = {
    "escola": ["microdados_ed_basica"],
    "curso": ["suplemento_cursos_tecnicos"],
}
NS_XLSX = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
EXTENSOES_GEO = {".gpkg", ".geojson", ".shp", ".fgb", ".kml"}
EXTENSOES_CSV = {".csv", ".tsv", ".txt"}


# ---------------------------------------------------------------- utilidades

def sair(mensagem):
    """Imprime mensagem de erro em stderr e encerra com código 1."""
    print("erro: " + mensagem, file=sys.stderr)
    sys.exit(1)


def chave_tabela(nome):
    """Normaliza nome de CSV do Censo Escolar: '.../Tabela_Escola_2025_V2.csv' -> 'escola'."""
    chave = Path(nome).stem.lower()
    chave = re.sub(r"^tabela_", "", chave)
    chave = re.sub(r"_v\d+$", "", chave)
    chave = re.sub(r"_?\d{4}$", "", chave)
    return chave


def slug_seguro(texto):
    """Gera slug seguro para nome de arquivo em temp/."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", texto).strip("_.")
    return slug[:90] or "dataset"


def formatar_bytes(tamanho):
    """Formata bytes de forma legível."""
    if tamanho is None:
        return ""
    valor = float(tamanho)
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if valor < 1024 or unidade == "TB":
            if unidade == "B":
                return f"{int(valor)} B"
            return f"{valor:.1f} {unidade}".replace(".", ",")
        valor /= 1024


def formatar_milhar(numero):
    """Formata inteiro com separador de milhar pt-BR: 212313 -> '212.313'."""
    return f"{int(numero):,}".replace(",", ".")


def escolher_nome_em_mapa(mapa, pedido, rotulo_tipo="tabela"):
    """Resolve nome curto por correspondência exata, apelido, prefixo ou trecho."""
    termo = pedido.lower()
    if termo in mapa:
        return termo
    for apelido in APELIDOS_TABELA.get(termo, []):
        if apelido in mapa:
            return apelido
    candidatas = [c for c in mapa if c.startswith(termo)] or [c for c in mapa if termo in c]
    if len(candidatas) == 1:
        return candidatas[0]
    disponiveis = ", ".join(sorted(mapa))
    if candidatas:
        sair(f"{rotulo_tipo.capitalize()} '{pedido}' ambígua ({', '.join(sorted(candidatas))}). Disponíveis: {disponiveis}")
    sair(f"{rotulo_tipo.capitalize()} '{pedido}' não encontrada. Disponíveis: {disponiveis}")


def deduplicar_colunas(nomes):
    """Garante nomes de coluna não vazios e únicos."""
    vistos = {}
    resultado = []
    for indice, nome in enumerate(nomes, 1):
        base = str(nome).strip() if nome is not None else ""
        if not base:
            base = f"coluna_{indice}"
        cont = vistos.get(base, 0)
        vistos[base] = cont + 1
        resultado.append(base if cont == 0 else f"{base}_{cont + 1}")
    return resultado


def valor_para_texto(valor):
    """Converte valor escalar/composto para string limpa, preservando vazio como ''."""
    if valor is None:
        return ""
    if isinstance(valor, (dict, list, tuple)):
        return json.dumps(valor, ensure_ascii=False)
    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass
    return str(valor)


# --------------------------------------------------------- detecção CSV/TSV

def detectar_encoding(amostra_bytes):
    """Detecta UTF-8 (retornando utf-8-sig para remover BOM) ou latin-1."""
    try:
        amostra_bytes.decode("utf-8")
        return "utf-8-sig"
    except UnicodeDecodeError as erro:
        if erro.start >= len(amostra_bytes) - 4:
            return "utf-8-sig"
        return "latin-1"


def detectar_separador(amostra_texto, extensao=""):
    """Infere o delimitador mais consistente entre ';', ',', '\\t' e '|'."""
    if extensao.lower() == ".tsv":
        return "\t"

    candidatos = [";", ",", "\t", "|"]
    melhor = None
    melhor_pontuacao = None

    for ordem, sep in enumerate(candidatos):
        try:
            leitor = csv.reader(io.StringIO(amostra_texto), delimiter=sep)
            linhas = [row for row in itertools.islice(leitor, 30) if row]
        except csv.Error:
            continue
        if not linhas:
            continue
        if len(linhas) >= 3 and not amostra_texto.endswith(("\n", "\r")):
            linhas = linhas[:-1]
        contagens = [len(row) for row in linhas]
        mediana = statistics.median(contagens)
        if mediana <= 1:
            continue
        cabecalho = contagens[0]
        consistencia = sum(1 for c in contagens if c == cabecalho) / len(contagens)
        pontuacao = (round(consistencia, 4), mediana, -ordem)
        if melhor_pontuacao is None or pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor = sep

    if melhor is not None:
        return melhor

    primeira_linha = amostra_texto.splitlines()[0] if amostra_texto else ""
    if "," in primeira_linha and ";" not in primeira_linha:
        return ","
    return ";"


# ---------------------------------------------------- leitura XLSX (stdlib)

def col_letra_para_indice(letra):
    """Converte letra de coluna do Excel ('A' -> 0, 'AA' -> 26)."""
    indice = 0
    for ch in letra:
        indice = indice * 26 + (ord(ch.upper()) - ord("A") + 1)
    return indice - 1


def _carregar_estrutura_xlsx(zf):
    """Retorna (shared_strings, [(nome_aba, caminho_xml), ...]) de um ZipFile .xlsx."""
    nomes = set(zf.namelist())
    compartilhados = []
    m = "{%s}" % NS_XLSX["m"]

    if "xl/sharedStrings.xml" in nomes:
        with zf.open("xl/sharedStrings.xml") as f:
            raiz = ET.parse(f).getroot()
        compartilhados = [
            "".join(t.text or "" for t in si.iter(m + "t"))
            for si in raiz.findall("m:si", NS_XLSX)
        ]

    with zf.open("xl/_rels/workbook.xml.rels") as f:
        rels = ET.parse(f).getroot()
    alvo = {r.get("Id"): r.get("Target") for r in rels}

    with zf.open("xl/workbook.xml") as f:
        livro = ET.parse(f).getroot()

    id_rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    abas = []
    sheets = livro.find("m:sheets", NS_XLSX)
    if sheets is not None:
        for aba in sheets:
            rel_id = aba.get(id_rel)
            destino = alvo.get(rel_id, "").lstrip("/")
            if destino and not destino.startswith("xl/"):
                destino = "xl/" + destino
            if destino in nomes:
                abas.append((aba.get("name", "Planilha").strip(), destino))
    return compartilhados, abas


def _extrair_valor_celula_xlsx(celula, compartilhados, m):
    """Extrai o texto de uma célula XML do .xlsx."""
    tipo = celula.get("t")
    if tipo == "inlineStr":
        inline = celula.find("m:is", NS_XLSX)
        if inline is None:
            return ""
        return "".join(t.text or "" for t in inline.iter(m + "t"))
    v = celula.find("m:v", NS_XLSX)
    if v is None or v.text is None:
        return ""
    if tipo == "s":
        idx = int(v.text)
        return compartilhados[idx] if 0 <= idx < len(compartilhados) else ""
    if tipo == "b":
        return "TRUE" if v.text == "1" else "FALSE"
    return v.text


def _ler_linhas_aba_xlsx(zf, destino, compartilhados, limite=None):
    """Lê linhas de uma aba .xlsx via iterparse, parando após 'limite' linhas."""
    m = "{%s}" % NS_XLSX["m"]
    tag_row = m + "row"
    linhas = []
    with zf.open(destino) as stream:
        for _evento, elem in ET.iterparse(stream, events=("end",)):
            if elem.tag != tag_row:
                continue
            valores = {}
            proximo_idx = 0
            for celula in elem.findall("m:c", NS_XLSX):
                ref = celula.get("r")
                if ref:
                    match = re.match(r"([A-Z]+)", ref)
                    idx = col_letra_para_indice(match.group(1)) if match else proximo_idx
                else:
                    idx = proximo_idx
                proximo_idx = idx + 1
                texto = _extrair_valor_celula_xlsx(celula, compartilhados, m)
                if texto != "":
                    valores[idx] = texto
            elem.clear()
            if valores:
                max_col = max(valores)
                linha = [valores.get(i, "") for i in range(max_col + 1)]
                linhas.append(linha)
                if limite is not None and len(linhas) >= limite:
                    break
    return linhas


def listar_abas_xlsx(caminho):
    """Lista os nomes das abas de um arquivo .xlsx."""
    with zipfile.ZipFile(caminho) as zf:
        _, abas = _carregar_estrutura_xlsx(zf)
    return [nome for nome, _ in abas]


def ler_xlsx_como_dataframe(caminho, aba=None, n=50, pular=0, amostra=False, semente=None):
    """Carrega linhas limitadas (ou amostra) de uma aba .xlsx em DataFrame de texto."""
    with zipfile.ZipFile(caminho) as zf:
        compartilhados, abas = _carregar_estrutura_xlsx(zf)
        if not abas:
            sair(f"Nenhuma planilha encontrada em {caminho}.")
        mapa_abas = {nome.lower(): (nome, destino) for nome, destino in abas}
        if aba:
            chave = escolher_nome_em_mapa(mapa_abas, aba, rotulo_tipo="aba")
            nome_aba, destino = mapa_abas[chave]
        else:
            nome_aba, destino = abas[0]

        limite = None if (amostra and n > 0) else (1 + pular + n)
        linhas = _ler_linhas_aba_xlsx(zf, destino, compartilhados, limite=limite)

    if not linhas:
        return pd.DataFrame(), [], nome_aba, 0

    colunas = deduplicar_colunas(linhas[0])
    dados = linhas[1:]
    total_dados = len(dados) if amostra or limite is None else None
    largura = max([len(colunas)] + [len(r) for r in dados]) if dados else len(colunas)
    if largura > len(colunas):
        extras = [f"coluna_{i}" for i in range(len(colunas) + 1, largura + 1)]
        colunas = deduplicar_colunas(colunas + extras)

    if pular > 0:
        dados = dados[pular:]

    if n == 0:
        return pd.DataFrame(columns=colunas), [], nome_aba, total_dados

    if amostra:
        rng = random.Random(semente)
        pares = list(enumerate(dados, start=pular + 1))
        if len(pares) > n:
            indices_sel = sorted(rng.sample(range(len(pares)), n))
            pares = [pares[i] for i in indices_sel]
    else:
        pares = list(enumerate(dados[:n], start=pular + 1))

    indices_linhas = [idx for idx, _ in pares]
    registros = [
        (r + [""] * (len(colunas) - len(r)))[: len(colunas)]
        for _, r in pares
    ]
    df = pd.DataFrame(registros, columns=colunas, dtype=str)
    return df, indices_linhas, nome_aba, total_dados


# ---------------------------------------------- dicionário INEP dentro de ZIP

def parsear_rotulos_categorias(categorias):
    """'1 - Federal\\n2 - Estadual' -> {'1': 'Federal', '2': 'Estadual'}."""
    resultado = {}
    for linha in (categorias or "").splitlines():
        achado = re.match(r"\s*(-?\w+)\s*[-–=:]\s*(.+)", linha)
        if achado:
            resultado[achado.group(1)] = achado.group(2).strip()
    return resultado


def ler_dicionario_inep_zip(zf, nome_tabela=None):
    """Lê dicionário de dados (.xlsx) presente no ZIP do Censo Escolar do INEP."""
    nomes_dic = [
        n for n in zf.namelist()
        if not n.endswith("/") and n.lower().endswith(".xlsx") and "dicion" in Path(n).name.lower()
    ]
    if not nomes_dic:
        return {}

    try:
        conteudo = zf.read(nomes_dic[0])
        with zipfile.ZipFile(io.BytesIO(conteudo)) as xlsx:
            compartilhados, abas = _carregar_estrutura_xlsx(xlsx)
            variaveis = []
            for nome_aba, destino in abas:
                linhas = _ler_linhas_aba_xlsx(xlsx, destino, compartilhados, limite=None)
                col_idx = None
                for linha in linhas:
                    if col_idx is None:
                        textos = {i: t.strip().lower() for i, t in enumerate(linha) if t.strip()}
                        achar = lambda trecho: next((i for i, t in textos.items() if trecho in t), None)  # noqa: E731
                        if achar("nome da vari") is not None:
                            col_idx = {
                                "variavel": achar("nome da vari"),
                                "descricao": achar("descri"),
                                "tipo": achar("tipo"),
                                "tamanho": achar("tam"),
                                "categorias": achar("categoria"),
                            }
                        continue
                    idx_var = col_idx["variavel"]
                    nome_var = linha[idx_var].strip() if idx_var < len(linha) else ""
                    if not re.fullmatch(r"[A-Z][A-Z0-9_]+", nome_var):
                        continue
                    item = {}
                    for k, i in col_idx.items():
                        item[k] = linha[i].strip() if (i is not None and i < len(linha)) else ""
                    item["aba"] = nome_aba
                    variaveis.append(item)
    except Exception:  # noqa: BLE001 - falha no dicionário não deve impedir prévia dos dados
        return {}

    mapa = {}
    tabela_norm = (nome_tabela or "").lower()
    for item in variaveis:
        var = item["variavel"]
        aba_norm = item["aba"].lower()
        prioridade = 1 if (tabela_norm and tabela_norm in aba_norm) else 0
        if var not in mapa or prioridade > mapa[var]["_prio"]:
            mapa[var] = {
                "descricao": item["descricao"],
                "tipo_dic": item["tipo"],
                "tamanho_dic": item["tamanho"],
                "categorias_texto": item["categorias"],
                "categorias": parsear_rotulos_categorias(item["categorias"]),
                "aba_dic": item["aba"],
                "_prio": prioridade,
            }

    for entry in mapa.values():
        entry.pop("_prio", None)
    return mapa


# ----------------------------------------------------------- leitores por formato

def carregar_csv_stream(abrir_fn, rotulo, extensao, args, tamanho_bytes=None):
    """Lê primeiras N linhas ou amostra reservatório uniforme de um stream CSV/TSV."""
    with abrir_fn() as f:
        amostra_bytes = f.read(1024 * 1024)

    encoding = args.encoding or detectar_encoding(amostra_bytes)
    amostra_texto = amostra_bytes.decode(encoding, errors="replace")
    sep = args.sep or detectar_separador(amostra_texto, extensao=extensao)

    skiprows = range(1, args.pular + 1) if args.pular > 0 else None
    opcoes_comuns = dict(
        sep=sep,
        encoding=encoding,
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )

    if args.linhas == 0:
        with abrir_fn() as f:
            df = pd.read_csv(f, nrows=0, **opcoes_comuns)
        indices_linhas = []
        total_linhas_fonte = None
    elif args.amostra:
        rng = random.Random(args.semente)
        heap = []  # min-heap de (-chave, linha_idx_real, lista_valores)
        total_apos_pular = 0
        colunas = None
        with abrir_fn() as f:
            leitor = pd.read_csv(f, skiprows=skiprows, chunksize=BLOCO, **opcoes_comuns)
            for bloco in leitor:
                if colunas is None:
                    colunas = list(bloco.columns)
                valores = bloco.values.tolist()
                for offset, linha in enumerate(valores):
                    linha_real = args.pular + total_apos_pular + offset + 1
                    chave = rng.random()
                    if len(heap) < args.linhas:
                        heapq.heappush(heap, (-chave, linha_real, linha))
                    elif chave < -heap[0][0]:
                        heapq.heapreplace(heap, (-chave, linha_real, linha))
                total_apos_pular += len(valores)

        if colunas is None:
            with abrir_fn() as f:
                df = pd.read_csv(f, nrows=0, **opcoes_comuns)
            indices_linhas = []
        else:
            selecionadas = sorted([(idx, vals) for _k, idx, vals in heap], key=lambda item: item[0])
            indices_linhas = [idx for idx, _ in selecionadas]
            df = pd.DataFrame([vals for _, vals in selecionadas], columns=colunas, dtype=str)
        total_linhas_fonte = args.pular + total_apos_pular
    else:
        with abrir_fn() as f:
            df = pd.read_csv(f, skiprows=skiprows, nrows=args.linhas, **opcoes_comuns)
        indices_linhas = [args.pular + i + 1 for i in range(len(df))]
        total_linhas_fonte = None

    df.columns = deduplicar_colunas(df.columns)
    meta = {
        "arquivo": str(args.arquivo),
        "rotulo": rotulo,
        "formato": "TSV" if sep == "\t" else "CSV",
        "tabela": None,
        "encoding": encoding,
        "separador": "\\t" if sep == "\t" else sep,
        "tamanho_bytes": tamanho_bytes,
        "total_linhas_fonte": total_linhas_fonte,
        "crs": None,
        "tipo_geometria": None,
        "modo_leitura": "amostra" if args.amostra else "primeiras",
        "pular": args.pular,
        "semente": args.semente if args.amostra else None,
    }
    return df, indices_linhas, meta


def _resumir_geometria(geom, shapely_mod):
    """Resume geometria sem despejar coordenadas gigantes de polígonos."""
    if geom is None or geom.is_empty:
        return ""
    tipo = geom.geom_type
    if tipo == "Point":
        return f"POINT ({geom.x:.6f}, {geom.y:.6f})"
    n_partes = int(shapely_mod.get_num_geometries(geom))
    n_vertices = int(shapely_mod.get_num_coordinates(geom))
    minx, miny, maxx, maxy = geom.bounds
    return (
        f"{tipo} ({n_partes} parte(s), {formatar_milhar(n_vertices)} vértices | "
        f"bbox: {minx:.4f}, {miny:.4f}, {maxx:.4f}, {maxy:.4f})"
    )


def carregar_geoespacial(caminho, args, formato=None):
    """Lê feições limitadas de GPKG, GeoJSON, Shapefile (.shp/.zip), FGB ou KML via pyogrio."""
    import pyogrio
    import shapely

    camadas_arr = pyogrio.list_layers(caminho)
    camadas = [(str(row[0]), str(row[1]) if len(row) > 1 and row[1] is not None else "") for row in camadas_arr]
    if not camadas:
        sair(f"Nenhuma camada encontrada em {caminho}.")

    if args.listar:
        print(f"== {caminho} ({len(camadas)} camada(s)) ==")
        for nome_camada, geom_tipo in camadas:
            info_c = pyogrio.read_info(caminho, layer=nome_camada)
            feats = info_c.get("features")
            feats_txt = formatar_milhar(feats) if feats is not None and feats >= 0 else "?"
            print(f"  {nome_camada:<32} {geom_tipo or '-':<16} {feats_txt} feições  CRS: {info_c.get('crs') or '-'}")
        sys.exit(0)

    mapa_camadas = {nome.lower(): nome for nome, _ in camadas}
    if args.tabela:
        chave = escolher_nome_em_mapa(mapa_camadas, args.tabela, rotulo_tipo="camada")
        camada = mapa_camadas[chave]
    elif len(camadas) == 1:
        camada = camadas[0][0]
    else:
        camada = camadas[0][0]

    info = pyogrio.read_info(caminho, layer=camada)
    total_feicoes = info.get("features")
    if total_feicoes is not None and total_feicoes < 0:
        total_feicoes = None
    crs = info.get("crs")
    tipo_geometria = info.get("geometry_type")
    ler_geom = not args.sem_geometria

    if args.linhas == 0:
        gdf = pyogrio.read_dataframe(caminho, layer=camada, read_geometry=ler_geom, max_features=0)
        indices_linhas = []
    elif args.amostra:
        rng = random.Random(args.semente)
        gdf = None
        indices_linhas = []
        if total_feicoes is not None and total_feicoes > args.pular:
            try:
                fids_df = pyogrio.read_dataframe(
                    caminho,
                    layer=camada,
                    columns=[],
                    read_geometry=False,
                    fid_as_index=True,
                )
                todos_fids = list(fids_df.index)[args.pular :]
                if todos_fids:
                    qtd = min(args.linhas, len(todos_fids))
                    posicoes = sorted(rng.sample(range(len(todos_fids)), qtd))
                    fids_escolhidos = [todos_fids[p] for p in posicoes]
                    gdf = pyogrio.read_dataframe(
                        caminho,
                        layer=camada,
                        read_geometry=ler_geom,
                        fids=fids_escolhidos,
                    )
                    indices_linhas = [args.pular + p + 1 for p in posicoes[: len(gdf)]]
            except Exception:
                gdf = None

        if gdf is None:
            gdf_full = pyogrio.read_dataframe(
                caminho,
                layer=camada,
                read_geometry=ler_geom,
                skip_features=args.pular,
            )
            if total_feicoes is None:
                total_feicoes = args.pular + len(gdf_full)
            qtd = min(args.linhas, len(gdf_full))
            posicoes = sorted(rng.sample(range(len(gdf_full)), qtd)) if qtd > 0 else []
            gdf = gdf_full.iloc[posicoes].reset_index(drop=True)
            indices_linhas = [args.pular + p + 1 for p in posicoes]
    else:
        gdf = pyogrio.read_dataframe(
            caminho,
            layer=camada,
            read_geometry=ler_geom,
            skip_features=args.pular,
            max_features=args.linhas,
        )
        indices_linhas = [args.pular + i + 1 for i in range(len(gdf))]

    geom_col = None
    if ler_geom and hasattr(gdf, "geometry"):
        try:
            geom_col = gdf.geometry.name
        except AttributeError:
            geom_col = None

    df_texto = pd.DataFrame(index=gdf.index)
    for col in gdf.columns:
        if col == geom_col:
            df_texto[col] = [_resumir_geometria(g, shapely) for g in gdf[col]]
        else:
            df_texto[col] = [valor_para_texto(v) for v in gdf[col]]

    df_texto.columns = deduplicar_colunas(df_texto.columns)
    ext = caminho.suffix.lower()
    rotulo_fmt = formato or {
        ".gpkg": "GeoPackage",
        ".geojson": "GeoJSON",
        ".json": "GeoJSON",
        ".shp": "Shapefile",
        ".fgb": "FlatGeobuf",
        ".kml": "KML",
    }.get(ext, "Geoespacial")

    meta = {
        "arquivo": str(caminho),
        "rotulo": f"{caminho.name} ({camada})" if len(camadas) > 1 else caminho.name,
        "formato": rotulo_fmt,
        "tabela": camada,
        "encoding": info.get("encoding"),
        "separador": None,
        "tamanho_bytes": caminho.stat().st_size,
        "total_linhas_fonte": total_feicoes,
        "crs": crs,
        "tipo_geometria": tipo_geometria,
        "geom_col": geom_col,
        "modo_leitura": "amostra" if args.amostra else "primeiras",
        "pular": args.pular,
        "semente": args.semente if args.amostra else None,
    }
    return df_texto, indices_linhas, meta, {}


def _mapear_csvs_zip(membros):
    """Mapeia {chave_curta: nome_interno} para CSV/TSV dentro de um ZIP."""
    todos = [n for n in membros if Path(n).suffix.lower() in (".csv", ".tsv")]
    em_dados = [n for n in todos if "/dados/" in n.lower() or n.lower().startswith("dados/")]
    escolhidos = em_dados or todos
    mapa = {}
    for nome in sorted(escolhidos):
        chave = chave_tabela(nome)
        if chave in mapa:
            chave = Path(nome).stem.lower()
        if chave in mapa:
            chave = nome.lower()
        mapa[chave] = nome
    return mapa


def carregar_zip(caminho, args):
    """Lê shapefile compactado ou CSV (único ou multi-tabela + dicionário) direto do ZIP."""
    with zipfile.ZipFile(caminho) as zf:
        membros = [
            n for n in zf.namelist()
            if not n.endswith("/") and not n.startswith("__MACOSX/")
        ]
        shps = [n for n in membros if n.lower().endswith(".shp")]
        if shps:
            return carregar_geoespacial(caminho, args, formato="Shapefile (ZIP)")

        tabelas = _mapear_csvs_zip(membros)
        if not tabelas:
            sair(f"Nenhum CSV, TSV ou Shapefile encontrado dentro de {caminho}.")

        tem_dic = any(
            n.lower().endswith(".xlsx") and "dicion" in Path(n).name.lower()
            for n in membros
        )

        if args.listar:
            print(f"== {caminho} ({len(tabelas)} tabela(s)) ==")
            for chave, nome in sorted(tabelas.items()):
                info = zf.getinfo(nome)
                print(f"  {chave:<18} {formatar_bytes(info.file_size):>10}  {nome}")
            if tem_dic:
                print("  (contém dicionário de dados .xlsx)")
            sys.exit(0)

        if args.tabela:
            chave = escolher_nome_em_mapa(tabelas, args.tabela, rotulo_tipo="tabela")
        elif len(tabelas) == 1:
            chave = next(iter(tabelas))
        else:
            linhas_ajuda = [
                f"  {c:<18} {formatar_bytes(zf.getinfo(n).file_size):>10}  {n}"
                for c, n in sorted(tabelas.items())
            ]
            sair(
                f"{caminho.name} contém {len(tabelas)} tabelas. Informe --tabela <nome>:\n"
                + "\n".join(linhas_ajuda)
            )

        nome_interno = tabelas[chave]
        info_csv = zf.getinfo(nome_interno)
        dicionario = ler_dicionario_inep_zip(zf, nome_tabela=chave) if tem_dic else {}
        if not args.encoding and tem_dic:
            # ZIPs do INEP usam latin-1 e podem não ter caracteres UTF-8 nos primeiros bytes;
            # ainda assim deixamos a detecção automática checar com segurança.
            pass

    def abrir_membro():
        zf_local = zipfile.ZipFile(caminho)
        stream = zf_local.open(nome_interno)

        class _StreamComZip:
            def __init__(self, z, s):
                self._z = z
                self._s = s

            def __enter__(self):
                return self._s

            def __exit__(self, *exc):
                self._s.close()
                self._z.close()

            def __getattr__(self, attr):
                return getattr(self._s, attr)

        return _StreamComZip(zf_local, stream)

    rotulo = f"{caminho.name} :: {chave} ({Path(nome_interno).name})"
    df, indices_linhas, meta = carregar_csv_stream(
        abrir_membro,
        rotulo=rotulo,
        extensao=Path(nome_interno).suffix,
        args=args,
        tamanho_bytes=info_csv.file_size,
    )
    meta["formato"] = f"{meta['formato']} (ZIP)"
    meta["tabela"] = chave
    return df, indices_linhas, meta, dicionario


def carregar_xlsx(caminho, args):
    """Lista abas ou lê aba selecionada de arquivo .xlsx sem openpyxl."""
    abas = listar_abas_xlsx(caminho)
    if args.listar:
        print(f"== {caminho} ({len(abas)} aba(s)) ==")
        for idx, nome in enumerate(abas, 1):
            print(f"  {idx:>2}. {nome}")
        sys.exit(0)

    df, indices_linhas, nome_aba, total_linhas = ler_xlsx_como_dataframe(
        caminho,
        aba=args.tabela,
        n=args.linhas,
        pular=args.pular,
        amostra=args.amostra,
        semente=args.semente,
    )
    meta = {
        "arquivo": str(caminho),
        "rotulo": f"{caminho.name} :: {nome_aba}" if len(abas) > 1 else caminho.name,
        "formato": "Excel (.xlsx)",
        "tabela": nome_aba,
        "encoding": "UTF-8 (XML)",
        "separador": None,
        "tamanho_bytes": caminho.stat().st_size,
        "total_linhas_fonte": total_linhas,
        "crs": None,
        "tipo_geometria": None,
        "modo_leitura": "amostra" if args.amostra else "primeiras",
        "pular": args.pular,
        "semente": args.semente if args.amostra else None,
    }
    return df, indices_linhas, meta, {}


def _registros_para_dataframe(pares):
    """Converte [(indice_linha, dict), ...] em DataFrame de texto."""
    if not pares:
        return pd.DataFrame(), []
    colunas = []
    vistas = set()
    for _, reg in pares:
        if isinstance(reg, dict):
            for k in reg:
                if k not in vistas:
                    vistas.add(k)
                    colunas.append(k)
        elif "valor" not in vistas:
            vistas.add("valor")
            colunas.append("valor")

    colunas_seg = deduplicar_colunas(colunas)
    linhas = []
    indices = []
    for idx, reg in pares:
        indices.append(idx)
        if isinstance(reg, dict):
            linhas.append([valor_para_texto(reg.get(k, "")) for k in colunas])
        else:
            linhas.append([valor_para_texto(reg) if k == "valor" else "" for k in colunas])
    return pd.DataFrame(linhas, columns=colunas_seg, dtype=str), indices


def carregar_json(caminho, args):
    """Carrega JSON, JSONL/NDJSON ou redireciona GeoJSON FeatureCollection."""
    ext = caminho.suffix.lower()
    if ext in (".jsonl", ".ndjson"):
        rng = random.Random(args.semente)
        pares = []
        heap = []
        total_validas = 0
        with open(caminho, "r", encoding=args.encoding or "utf-8-sig") as f:
            for linha_txt in f:
                linha_txt = linha_txt.strip()
                if not linha_txt:
                    continue
                total_validas += 1
                if total_validas <= args.pular:
                    continue
                obj = json.loads(linha_txt)
                if args.linhas == 0:
                    pares = [(total_validas, obj)]
                    break
                if args.amostra:
                    chave = rng.random()
                    if len(heap) < args.linhas:
                        heapq.heappush(heap, (-chave, total_validas, obj))
                    elif chave < -heap[0][0]:
                        heapq.heapreplace(heap, (-chave, total_validas, obj))
                else:
                    pares.append((total_validas, obj))
                    if len(pares) >= args.linhas:
                        break

        if args.amostra and args.linhas > 0:
            pares = sorted([(idx, o) for _k, idx, o in heap], key=lambda item: item[0])
            total_fonte = total_validas
        else:
            total_fonte = None

        df, indices_linhas = _registros_para_dataframe(pares)
        if args.linhas == 0:
            df = df.iloc[0:0]
            indices_linhas = []
        meta = {
            "arquivo": str(caminho),
            "rotulo": caminho.name,
            "formato": "JSONL",
            "tabela": None,
            "encoding": args.encoding or "utf-8-sig",
            "separador": None,
            "tamanho_bytes": caminho.stat().st_size,
            "total_linhas_fonte": total_fonte,
            "crs": None,
            "tipo_geometria": None,
            "modo_leitura": "amostra" if args.amostra else "primeiras",
            "pular": args.pular,
            "semente": args.semente if args.amostra else None,
        }
        return df, indices_linhas, meta, {}

    with open(caminho, "r", encoding=args.encoding or "utf-8-sig") as f:
        dados = json.load(f)

    if isinstance(dados, dict) and dados.get("type") == "FeatureCollection" and isinstance(dados.get("features"), list):
        return carregar_geoespacial(caminho, args, formato="GeoJSON")

    tabela_chave = None
    if isinstance(dados, dict):
        listas_dict = {
            k: v for k, v in dados.items()
            if isinstance(v, list) and (not v or isinstance(v[0], dict))
        }
        if args.tabela:
            if args.tabela not in dados or not isinstance(dados[args.tabela], list):
                sair(f"Chave '{args.tabela}' não é uma lista em {caminho.name}.")
            tabela_chave = args.tabela
            registros = dados[tabela_chave]
        elif len(listas_dict) == 1:
            tabela_chave, registros = next(iter(listas_dict.items()))
        else:
            registros = [dados]
    elif isinstance(dados, list):
        registros = dados
    else:
        registros = [{"valor": dados}]

    total_fonte = len(registros)
    recorte = registros[args.pular :]
    if args.linhas == 0:
        pares = [(1, recorte[0])] if recorte else []
        df, _ = _registros_para_dataframe(pares)
        df = df.iloc[0:0]
        indices_linhas = []
    elif args.amostra:
        rng = random.Random(args.semente)
        qtd = min(args.linhas, len(recorte))
        posicoes = sorted(rng.sample(range(len(recorte)), qtd)) if qtd > 0 else []
        pares = [(args.pular + p + 1, recorte[p]) for p in posicoes]
        df, indices_linhas = _registros_para_dataframe(pares)
    else:
        pares = [(args.pular + i + 1, item) for i, item in enumerate(recorte[: args.linhas])]
        df, indices_linhas = _registros_para_dataframe(pares)

    meta = {
        "arquivo": str(caminho),
        "rotulo": f"{caminho.name} :: {tabela_chave}" if tabela_chave else caminho.name,
        "formato": "JSON",
        "tabela": tabela_chave,
        "encoding": args.encoding or "utf-8-sig",
        "separador": None,
        "tamanho_bytes": caminho.stat().st_size,
        "total_linhas_fonte": total_fonte,
        "crs": None,
        "tipo_geometria": None,
        "modo_leitura": "amostra" if args.amostra else "primeiras",
        "pular": args.pular,
        "semente": args.semente if args.amostra else None,
    }
    return df, indices_linhas, meta, {}


def carregar_dados(args):
    """Seleciona o leitor apropriado pela extensão do arquivo."""
    caminho = Path(args.arquivo)
    if not caminho.exists():
        sair(f"Arquivo não encontrado: {caminho}")
    if not caminho.is_file():
        sair(f"O caminho informado não é um arquivo: {caminho}")

    ext = caminho.suffix.lower()
    if ext == ".zip":
        return carregar_zip(caminho, args)
    if ext in EXTENSOES_GEO:
        return carregar_geoespacial(caminho, args)
    if ext == ".xlsx":
        return carregar_xlsx(caminho, args)
    if ext in (".json", ".jsonl", ".ndjson"):
        return carregar_json(caminho, args)
    if ext in EXTENSOES_CSV or ext == "":
        if args.listar:
            sair("--listar só se aplica a arquivos ZIP, geoespaciais (.gpkg) ou Excel (.xlsx).")
        df, indices_linhas, meta = carregar_csv_stream(
            lambda: open(caminho, "rb"),
            rotulo=caminho.name,
            extensao=ext,
            args=args,
            tamanho_bytes=caminho.stat().st_size,
        )
        return df, indices_linhas, meta, {}

    sair(f"Formato não suportado: '{ext}'. Use CSV, TSV, ZIP, GPKG, GeoJSON, Shapefile, XLSX ou JSON/JSONL.")


# ------------------------------------------------------- filtro e perfilamento

def aplicar_selecao_colunas(df, args, dicionario):
    """Aplica --colunas e --filtro-colunas sobre o DataFrame carregado."""
    colunas = list(df.columns)

    if args.colunas:
        pedidas = [c.strip() for c in args.colunas.split(",") if c.strip()]
        existentes = set(colunas)
        faltando = [c for c in pedidas if c not in existentes]
        if faltando:
            parecidas = [c for c in colunas if any(f.lower() in c.lower() for f in faltando)]
            dica = f" Parecidas: {', '.join(parecidas[:15])}" if parecidas else ""
            sair(f"Colunas inexistentes: {', '.join(faltando)}.{dica}")
        colunas = pedidas

    if args.filtro_colunas:
        termo = args.filtro_colunas.lower()
        filtradas = []
        for c in colunas:
            info_dic = dicionario.get(c) or dicionario.get(c.upper()) or {}
            desc = info_dic.get("descricao", "").lower()
            if termo in c.lower() or termo in desc:
                filtradas.append(c)
        if not filtradas:
            sair(f"Nenhuma coluna corresponde a --filtro-colunas '{args.filtro_colunas}'.")
        colunas = filtradas

    return df[colunas]


def _eh_inteiro_sem_zero_esq(valores):
    """True se todos forem inteiros sem zero à esquerda (preserva CEPs/códigos como texto)."""
    for v in valores:
        if not re.fullmatch(r"-?\d+", v):
            return False
        digitos = v.lstrip("-")
        if len(digitos) > 1 and digitos.startswith("0"):
            return False
    return True


def _inferir_tipo_amostra(valores, eh_geom=False):
    """Infere tipo aparente da coluna a partir dos valores não vazios da amostra."""
    if eh_geom:
        return "geometria"
    if not valores:
        return "vazia"
    if all(v.lower() in {"true", "false", "sim", "nao", "não"} for v in valores):
        return "booleano"
    if _eh_inteiro_sem_zero_esq(valores):
        return "inteiro"
    if all(re.fullmatch(r"-?\d+(?:[.,]\d+)?", v) for v in valores) and any(("." in v or "," in v) for v in valores):
        return "decimal"
    if all(re.match(r"^(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})([ T]\d{2}:\d{2}.*)?$", v) for v in valores):
        return "data"
    return "texto"


def analisar_colunas(df, dicionario, geom_col=None):
    """Constrói metadados e estatísticas por coluna sobre as linhas carregadas."""
    n_linhas = len(df)
    perfis = []
    for idx, nome in enumerate(df.columns):
        serie = [valor_para_texto(v) for v in df[nome].tolist()]
        nao_vazios = [v.strip() for v in serie if v and v.strip()]
        preenchidas = len(nao_vazios)
        vazias = n_linhas - preenchidas
        pct = round(100.0 * preenchidas / n_linhas, 1) if n_linhas else 0.0

        vistos = []
        vistos_set = set()
        for v in nao_vazios:
            if v not in vistos_set:
                vistos_set.add(v)
                vistos.append(v[:77] + "..." if len(v) > 80 else v)
                if len(vistos) >= 5:
                    break

        contagem = Counter(nao_vazios)
        top_valores = [[k[:57] + "..." if len(k) > 60 else k, int(cnt)] for k, cnt in contagem.most_common(5)]

        dic = dicionario.get(nome) or dicionario.get(nome.upper()) or {}
        perfis.append(
            {
                "idx": idx,
                "numero": idx + 1,
                "nome": nome,
                "tipo": _inferir_tipo_amostra(nao_vazios, eh_geom=(nome == geom_col)),
                "preenchidas": preenchidas,
                "vazias": vazias,
                "pct_preenchidas": pct,
                "distintos": len(contagem),
                "exemplos": vistos,
                "top_valores": top_valores,
                "descricao": dic.get("descricao", ""),
                "tipo_dic": dic.get("tipo_dic", ""),
                "tamanho_dic": dic.get("tamanho_dic", ""),
                "categorias_texto": dic.get("categorias_texto", ""),
                "categorias": dic.get("categorias", {}),
            }
        )
    return perfis


# --------------------------------------------------------------- gerador HTML

TEMPLATE_HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITULO__</title>
<style>
  :root {
    --bg: #f8fafc;
    --surface: #ffffff;
    --surface-2: #f1f5f9;
    --border: #cbd5e1;
    --border-soft: #e2e8f0;
    --text: #0f172a;
    --text-muted: #475569;
    --accent: #2563eb;
    --accent-soft: #dbeafe;
    --accent-text: #1e40af;
    --ok: #16a34a;
    --warn: #d97706;
    --empty: #94a3b8;
    --row-hover: #eff6ff;
    --shadow: 0 10px 30px rgba(15, 23, 42, 0.14);
    --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    --sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  [data-theme="dark"] {
    --bg: #0b1220;
    --surface: #111827;
    --surface-2: #1e293b;
    --border: #334155;
    --border-soft: #1f2937;
    --text: #e2e8f0;
    --text-muted: #94a3b8;
    --accent: #60a5fa;
    --accent-soft: #1e3a8a;
    --accent-text: #bfdbfe;
    --ok: #4ade80;
    --warn: #fbbf24;
    --empty: #64748b;
    --row-hover: #1e293b;
    --shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; font-family: var(--sans); background: var(--bg); color: var(--text); }
  .app { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

  header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 0.7rem 1rem 0.55rem;
    flex: 0 0 auto;
  }
  .header-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 0.75rem; flex-wrap: wrap; }
  .title-wrap h1 { margin: 0; font-size: 1.05rem; font-weight: 700; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
  .subtitle { font-size: 0.76rem; color: var(--text-muted); margin-top: 0.18rem; word-break: break-all; font-family: var(--mono); }
  .chips { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.5rem; }
  .chip {
    display: inline-flex; align-items: center; gap: 0.25rem;
    padding: 0.16rem 0.5rem; border-radius: 999px; font-size: 0.75rem;
    background: var(--surface-2); border: 1px solid var(--border-soft); color: var(--text);
  }
  .chip strong { font-weight: 600; }
  .chip-accent { background: var(--accent-soft); border-color: transparent; color: var(--accent-text); }

  .tabs-bar {
    display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 0 1rem; flex: 0 0 auto;
  }
  .tabs { display: flex; gap: 0.25rem; }
  .tab-btn {
    border: none; background: transparent; color: var(--text-muted);
    padding: 0.55rem 0.85rem; font-size: 0.85rem; font-weight: 600;
    cursor: pointer; border-bottom: 2px solid transparent;
  }
  .tab-btn:hover { color: var(--text); }
  .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }

  .btn {
    display: inline-flex; align-items: center; gap: 0.3rem;
    border: 1px solid var(--border); background: var(--surface); color: var(--text);
    padding: 0.32rem 0.62rem; border-radius: 6px; font-size: 0.78rem; font-weight: 500;
    cursor: pointer; white-space: nowrap;
  }
  .btn:hover { background: var(--surface-2); }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn-primary { background: var(--accent); border-color: var(--accent); color: #ffffff; }
  .btn-primary:hover { filter: brightness(1.08); background: var(--accent); }
  .btn-xs { padding: 0.18rem 0.45rem; font-size: 0.72rem; }

  input[type="text"], input[type="search"], input[type="number"] {
    background: var(--surface); color: var(--text);
    border: 1px solid var(--border); border-radius: 6px;
    padding: 0.32rem 0.55rem; font-size: 0.82rem; outline: none;
  }
  input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.18); }

  main { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
  .tab-panel { display: none; flex: 1 1 auto; min-height: 0; }
  .tab-panel.active { display: flex; }

  /* Tab 1: Tabela */
  .table-layout { display: flex; width: 100%; height: 100%; min-height: 0; }
  .sidebar {
    width: 300px; flex: 0 0 300px; background: var(--surface);
    border-right: 1px solid var(--border); display: flex; flex-direction: column; min-height: 0;
  }
  .sidebar.collapsed { display: none; }
  .sidebar-head { padding: 0.65rem; border-bottom: 1px solid var(--border-soft); display: flex; flex-direction: column; gap: 0.45rem; }
  .sidebar-title { display: flex; align-items: center; justify-content: space-between; font-size: 0.82rem; font-weight: 700; }
  .pills { display: flex; flex-wrap: wrap; gap: 0.25rem; }
  .pill {
    border: 1px solid var(--border); background: var(--surface); color: var(--text-muted);
    padding: 0.14rem 0.48rem; border-radius: 999px; font-size: 0.72rem; cursor: pointer;
  }
  .pill.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent-text); font-weight: 600; }
  .bulk-actions { display: flex; flex-wrap: wrap; gap: 0.25rem; }
  .col-list { flex: 1 1 auto; overflow-y: auto; padding: 0.35rem; }
  .col-item {
    display: flex; align-items: flex-start; gap: 0.45rem; padding: 0.35rem 0.4rem;
    border-radius: 6px; cursor: pointer; font-size: 0.79rem;
  }
  .col-item:hover { background: var(--surface-2); }
  .col-item input { margin-top: 0.15rem; cursor: pointer; }
  .col-item-meta { min-width: 0; flex: 1; }
  .col-item-name { display: flex; align-items: center; justify-content: space-between; gap: 0.3rem; font-weight: 600; }
  .col-item-name span.cname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--mono); font-size: 0.76rem; }
  .col-item-pct { font-size: 0.7rem; color: var(--text-muted); flex-shrink: 0; }
  .col-item-desc { font-size: 0.71rem; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 0.08rem; }

  .grid-area { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; min-height: 0; }
  .toolbar {
    display: flex; align-items: center; flex-wrap: wrap; gap: 0.5rem;
    padding: 0.55rem 0.75rem; background: var(--surface); border-bottom: 1px solid var(--border-soft);
  }
  .toolbar label.chk { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.78rem; cursor: pointer; user-select: none; }
  .toolbar .spacer { flex: 1 1 auto; }
  .status-count { font-size: 0.76rem; color: var(--text-muted); }

  .table-scroll { flex: 1 1 auto; overflow: auto; position: relative; background: var(--bg); }
  table.data-grid { border-collapse: separate; border-spacing: 0; width: max-content; min-width: 100%; font-size: 0.8rem; }
  table.data-grid thead th {
    position: sticky; top: 0; z-index: 3; background: var(--surface-2);
    border-bottom: 1px solid var(--border); border-right: 1px solid var(--border-soft);
    padding: 0.42rem 0.6rem; text-align: left; font-weight: 700; cursor: pointer; user-select: none;
    white-space: nowrap; max-width: 280px; overflow: hidden; text-overflow: ellipsis;
  }
  table.data-grid thead th:hover { background: var(--accent-soft); }
  table.data-grid thead th.rownum-col { left: 0; z-index: 4; cursor: default; text-align: right; min-width: 54px; }
  table.data-grid thead th.rownum-col:hover { background: var(--surface-2); }
  table.data-grid tbody td {
    background: var(--surface); border-bottom: 1px solid var(--border-soft); border-right: 1px solid var(--border-soft);
    padding: 0.34rem 0.6rem; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    vertical-align: top; cursor: pointer;
  }
  table.data-grid tbody tr:hover td { background: var(--row-hover); }
  table.data-grid tbody td.rownum-col {
    position: sticky; left: 0; z-index: 2; background: var(--surface-2);
    color: var(--text-muted); text-align: right; font-family: var(--mono); font-size: 0.74rem;
    min-width: 54px; font-weight: 600;
  }
  table.data-grid tbody tr:hover td.rownum-col { background: var(--accent-soft); color: var(--accent-text); }
  td.cell-empty { color: var(--empty); font-style: italic; }
  .sort-ind { margin-left: 0.25rem; color: var(--accent); font-size: 0.72rem; }
  .th-sub { display: block; font-size: 0.66rem; font-weight: 500; color: var(--text-muted); }

  /* Tab 2: Colunas */
  .schema-wrap { width: 100%; display: flex; flex-direction: column; min-height: 0; }
  .schema-scroll { flex: 1 1 auto; overflow: auto; padding: 0.75rem; }
  table.schema-table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); font-size: 0.8rem; }
  table.schema-table th, table.schema-table td { border-bottom: 1px solid var(--border-soft); padding: 0.45rem 0.6rem; text-align: left; vertical-align: top; }
  table.schema-table th { position: sticky; top: 0; background: var(--surface-2); border-bottom: 1px solid var(--border); z-index: 2; }
  .type-badge {
    display: inline-block; padding: 0.1rem 0.4rem; border-radius: 4px;
    font-family: var(--mono); font-size: 0.71rem; background: var(--surface-2); border: 1px solid var(--border-soft);
  }
  .type-inteiro, .type-decimal { background: rgba(37, 99, 235, 0.12); color: var(--accent); border-color: transparent; }
  .type-geometria { background: rgba(22, 163, 74, 0.14); color: var(--ok); border-color: transparent; }
  .type-vazia { color: var(--empty); }
  .bar-wrap { display: flex; align-items: center; gap: 0.4rem; min-width: 120px; }
  .bar { flex: 1; height: 7px; border-radius: 999px; background: var(--surface-2); overflow: hidden; }
  .bar-fill { height: 100%; background: var(--accent); }
  .ex-chip {
    display: inline-block; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    padding: 0.08rem 0.35rem; margin: 0.1rem 0.18rem 0.1rem 0; border-radius: 4px;
    background: var(--surface-2); font-family: var(--mono); font-size: 0.72rem;
  }
  details.dic-cats { margin-top: 0.25rem; font-size: 0.74rem; color: var(--text-muted); }
  details.dic-cats summary { cursor: pointer; color: var(--accent); }
  details.dic-cats pre { margin: 0.25rem 0 0; white-space: pre-wrap; font-family: var(--mono); font-size: 0.71rem; background: var(--surface-2); padding: 0.35rem; border-radius: 4px; }

  /* Tab 3: Vertical */
  .vertical-wrap { width: 100%; display: flex; flex-direction: column; min-height: 0; }
  .vertical-scroll { flex: 1 1 auto; overflow-y: auto; padding: 0.75rem 1rem; }
  .vertical-card {
    max-width: 1100px; margin: 0 auto; background: var(--surface);
    border: 1px solid var(--border); border-radius: 8px; overflow: hidden;
  }
  .v-row {
    display: grid; grid-template-columns: minmax(210px, 320px) 1fr; gap: 0.75rem;
    padding: 0.48rem 0.85rem; border-bottom: 1px solid var(--border-soft); font-size: 0.82rem;
  }
  .v-row:last-child { border-bottom: none; }
  .v-row:hover { background: var(--row-hover); }
  .v-key { font-family: var(--mono); font-weight: 600; font-size: 0.78rem; word-break: break-word; }
  .v-key-desc { display: block; font-family: var(--sans); font-weight: 400; font-size: 0.72rem; color: var(--text-muted); margin-top: 0.1rem; }
  .v-val { white-space: pre-wrap; word-break: break-word; font-family: var(--mono); font-size: 0.79rem; }
  .v-val.empty { color: var(--empty); font-style: italic; font-family: var(--sans); }
  .dic-pill {
    display: inline-block; margin-left: 0.45rem; padding: 0.08rem 0.42rem;
    border-radius: 999px; background: var(--accent-soft); color: var(--accent-text);
    font-family: var(--sans); font-size: 0.72rem; font-weight: 600;
  }

  .banner {
    margin: 1rem; padding: 0.85rem 1rem; border-radius: 8px;
    background: var(--surface); border: 1px solid var(--border); color: var(--text-muted); font-size: 0.86rem;
  }

  /* Modal */
  .modal-backdrop {
    display: none; position: fixed; inset: 0; z-index: 30;
    background: rgba(15, 23, 42, 0.55); align-items: center; justify-content: center; padding: 1rem;
  }
  .modal-backdrop.open { display: flex; }
  .modal {
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    box-shadow: var(--shadow); width: min(760px, 96vw); max-height: 85vh; display: flex; flex-direction: column;
  }
  .modal-head {
    display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;
    padding: 0.7rem 0.95rem; border-bottom: 1px solid var(--border-soft);
  }
  .modal-head h2 { margin: 0; font-size: 0.94rem; font-family: var(--mono); }
  .modal-body { padding: 0.85rem 0.95rem; overflow-y: auto; font-size: 0.83rem; }
  .modal-val {
    background: var(--surface-2); border: 1px solid var(--border-soft); border-radius: 6px;
    padding: 0.65rem; font-family: var(--mono); font-size: 0.8rem;
    white-space: pre-wrap; word-break: break-word; max-height: 45vh; overflow-y: auto;
  }
  .modal-foot { display: flex; justify-content: flex-end; gap: 0.5rem; padding: 0.6rem 0.95rem; border-top: 1px solid var(--border-soft); }
  .toast {
    position: fixed; right: 1rem; bottom: 1rem; z-index: 40;
    background: var(--text); color: var(--surface); padding: 0.45rem 0.8rem;
    border-radius: 6px; font-size: 0.78rem; opacity: 0; pointer-events: none; transition: opacity 0.2s;
  }
  .toast.show { opacity: 0.95; }

  @media (max-width: 820px) {
    .sidebar { width: 230px; flex-basis: 230px; }
    .v-row { grid-template-columns: 1fr; gap: 0.25rem; }
  }
</style>
</head>
<body>
<div class="app">
  <header>
    <div class="header-top">
      <div class="title-wrap">
        <h1 id="hdr-title"></h1>
        <div class="subtitle" id="hdr-path"></div>
      </div>
      <div>
        <button class="btn" id="btn-theme" type="button">Tema escuro</button>
      </div>
    </div>
    <div class="chips" id="hdr-chips"></div>
  </header>

  <div class="tabs-bar">
    <div class="tabs">
      <button class="tab-btn active" data-tab="tabela" type="button">Tabela</button>
      <button class="tab-btn" data-tab="colunas" type="button">Colunas (Esquema)</button>
      <button class="tab-btn" data-tab="vertical" type="button">Vertical (Registros)</button>
    </div>
    <div class="status-count" id="global-status"></div>
  </div>

  <main>
    <!-- Aba 1: Tabela -->
    <section class="tab-panel active" id="tab-tabela">
      <div class="table-layout">
        <aside class="sidebar" id="col-sidebar">
          <div class="sidebar-head">
            <div class="sidebar-title">
              <span>Colunas</span>
              <span id="side-count" class="status-count"></span>
            </div>
            <input type="search" id="side-search" placeholder="Buscar coluna ou descrição...">
            <div class="pills" id="side-pills">
              <button class="pill active" data-filter="todas" type="button">Todas</button>
              <button class="pill" data-filter="preenchidas" type="button">Preenchidas</button>
              <button class="pill" data-filter="vazias" type="button">Vazias</button>
            </div>
            <div class="bulk-actions">
              <button class="btn btn-xs" id="btn-mark-filtered" type="button">Marcar filtradas</button>
              <button class="btn btn-xs" id="btn-unmark-filtered" type="button">Desmarcar filtradas</button>
              <button class="btn btn-xs" id="btn-first-15" type="button">Primeiras 15</button>
              <button class="btn btn-xs" id="btn-mark-all" type="button">Todas</button>
            </div>
          </div>
          <div class="col-list" id="col-list"></div>
        </aside>

        <div class="grid-area">
          <div class="toolbar">
            <button class="btn" id="btn-toggle-sidebar" type="button">Ocultar painel</button>
            <input type="search" id="row-search" placeholder="Filtrar nas linhas carregadas..." style="min-width: 220px;">
            <label class="chk"><input type="checkbox" id="chk-hide-empty"> Ocultar colunas vazias</label>
            <label class="chk" id="wrap-dic-labels" style="display:none;"><input type="checkbox" id="chk-dic-labels" checked> Rótulos do dicionário</label>
            <button class="btn" id="btn-copy-cols" type="button">Copiar colunas visíveis</button>
            <span class="spacer"></span>
            <span class="status-count" id="table-status"></span>
          </div>
          <div class="table-scroll" id="table-scroll"></div>
        </div>
      </div>
    </section>

    <!-- Aba 2: Colunas -->
    <section class="tab-panel" id="tab-colunas">
      <div class="schema-wrap">
        <div class="toolbar">
          <input type="search" id="schema-search" placeholder="Buscar por nome, descrição, exemplo ou categoria..." style="min-width: 280px;">
          <div class="pills" id="schema-pills">
            <button class="pill active" data-filter="todas" type="button">Todas</button>
            <button class="pill" data-filter="preenchidas" type="button">Preenchidas</button>
            <button class="pill" data-filter="vazias" type="button">Vazias</button>
            <button class="pill" data-filter="numericas" type="button">Numéricas</button>
            <button class="pill" data-filter="texto" type="button">Texto</button>
          </div>
          <span class="spacer"></span>
          <span class="status-count" id="schema-status"></span>
        </div>
        <div class="schema-scroll" id="schema-scroll"></div>
      </div>
    </section>

    <!-- Aba 3: Vertical -->
    <section class="tab-panel" id="tab-vertical">
      <div class="vertical-wrap">
        <div class="toolbar">
          <button class="btn" id="btn-v-prev" type="button">← Anterior</button>
          <span style="font-size:0.8rem;">Registro</span>
          <input type="number" id="v-pos" min="1" value="1" style="width: 72px;">
          <span id="v-total" class="status-count"></span>
          <button class="btn" id="btn-v-next" type="button">Próxima →</button>
          <input type="search" id="v-search" placeholder="Filtrar campo ou valor..." style="min-width: 210px;">
          <label class="chk"><input type="checkbox" id="v-hide-empty"> Ocultar vazias</label>
          <label class="chk"><input type="checkbox" id="v-only-checked"> Só colunas marcadas</label>
          <label class="chk" id="wrap-v-dic" style="display:none;"><input type="checkbox" id="v-dic-labels" checked> Rótulos do dicionário</label>
        </div>
        <div class="vertical-scroll" id="vertical-scroll"></div>
      </div>
    </section>
  </main>
</div>

<!-- Modal de inspeção de célula -->
<div class="modal-backdrop" id="cell-modal">
  <div class="modal" role="dialog" aria-modal="true">
    <div class="modal-head">
      <h2 id="modal-title"></h2>
      <button class="btn btn-xs" id="modal-close" type="button">Fechar</button>
    </div>
    <div class="modal-body">
      <div id="modal-meta" style="margin-bottom:0.5rem;color:var(--text-muted);font-size:0.78rem;"></div>
      <div class="modal-val" id="modal-val"></div>
      <div id="modal-dic" style="margin-top:0.65rem;"></div>
    </div>
    <div class="modal-foot">
      <button class="btn" id="modal-open-vertical" type="button">Ver linha completa na aba Vertical</button>
      <button class="btn btn-primary" id="modal-copy" type="button">Copiar valor</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script id="dados-preview" type="application/json">__JSON_DADOS__</script>
<script>
(function () {
  "use strict";

  const DATA = JSON.parse(document.getElementById("dados-preview").textContent);
  const META = DATA.meta || {};
  const COLS = DATA.colunas || [];
  const ROWS = DATA.linhas || [];
  const ROW_INDICES = DATA.indices_linhas || [];
  const HAS_DIC = COLS.some((c) => Boolean(c.descricao || (c.categorias && Object.keys(c.categorias).length)));
  const HAS_DIC_CATS = COLS.some((c) => c.categorias && Object.keys(c.categorias).length);
  const HAS_GEOM = COLS.some((c) => c.tipo === "geometria");

  const state = {
    tab: "tabela",
    selected: new Set(COLS.map((c) => c.idx)),
    sideFilter: "todas",
    sideQuery: "",
    hideEmptyCols: false,
    showDicLabels: true,
    rowQuery: "",
    sortCol: null,
    sortDir: 0, // 0=original, 1=asc, -1=desc
    schemaFilter: "todas",
    schemaQuery: "",
    vPos: 0,
    vQuery: "",
    vHideEmpty: false,
    vOnlyChecked: false,
    vShowDic: true,
    modalRowPos: 0,
    modalRawVal: ""
  };

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === undefined || v === null) continue;
        if (k === "className") node.className = v;
        else if (k === "textContent") node.textContent = v;
        else if (k === "title") node.title = v;
        else if (k === "checked") node.checked = Boolean(v);
        else if (k === "disabled") node.disabled = Boolean(v);
        else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2).toLowerCase(), v);
        else node.setAttribute(k, String(v));
      }
    }
    if (children !== undefined) {
      const list = Array.isArray(children) ? children : [children];
      for (const ch of list) {
        if (ch === null || ch === undefined) continue;
        node.appendChild(typeof ch === "string" ? document.createTextNode(ch) : ch);
      }
    }
    return node;
  }

  function showToast(msg) {
    const toast = document.getElementById("toast");
    toast.textContent = msg;
    toast.classList.add("show");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => toast.classList.remove("show"), 2000);
  }

  function copyText(texto, okMsg) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto).then(() => showToast(okMsg)).catch(() => fallbackCopy(texto, okMsg));
    } else {
      fallbackCopy(texto, okMsg);
    }
  }

  function fallbackCopy(texto, okMsg) {
    const ta = el("textarea", { style: "position:fixed;left:-9999px;" }, texto);
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      showToast(okMsg);
    } catch (_e) {
      showToast("Não foi possível copiar automaticamente.");
    }
    document.body.removeChild(ta);
  }

  function formatInt(n) {
    return Number(n).toLocaleString("pt-BR");
  }

  function formatBytes(b) {
    if (b === null || b === undefined) return "";
    let v = Number(b);
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return i === 0 ? v + " B" : v.toFixed(1).replace(".", ",") + " " + units[i];
  }

  function parseNumeric(raw) {
    const s = String(raw || "").trim();
    if (!s) return NaN;
    const norm = s.includes(",") && !s.includes(".") ? s.replace(",", ".") : s;
    const num = Number(norm);
    return Number.isFinite(num) ? num : NaN;
  }

  function getDicLabel(col, val) {
    if (!col || !col.categorias) return "";
    const k = String(val || "").trim();
    return col.categorias[k] || "";
  }

  function getVisibleCols() {
    return COLS.filter((c) => state.selected.has(c.idx) && (!state.hideEmptyCols || c.preenchidas > 0));
  }

  function getSidebarCols() {
    const q = state.sideQuery.trim().toLowerCase();
    return COLS.filter((c) => {
      if (state.sideFilter === "preenchidas" && c.preenchidas === 0) return false;
      if (state.sideFilter === "vazias" && c.preenchidas > 0) return false;
      if (state.sideFilter === "dicionario" && !c.descricao && !Object.keys(c.categorias || {}).length) return false;
      if (q) {
        const hay = (c.nome + " " + (c.descricao || "")).toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function getFilteredSortedRowPositions() {
    const q = state.rowQuery.trim().toLowerCase();
    const visCols = getVisibleCols();
    const positions = [];
    for (let i = 0; i < ROWS.length; i++) {
      if (!q) {
        positions.push(i);
        continue;
      }
      const row = ROWS[i];
      let matched = false;
      const scanCols = visCols.length ? visCols : COLS;
      for (const c of scanCols) {
        const v = String(row[c.idx] || "").toLowerCase();
        const rot = HAS_DIC_CATS ? getDicLabel(c, row[c.idx]).toLowerCase() : "";
        if (v.includes(q) || (rot && rot.includes(q))) {
          matched = true;
          break;
        }
      }
      if (matched) positions.push(i);
    }

    if (state.sortCol !== null && state.sortDir !== 0) {
      const col = COLS[state.sortCol];
      const isNum = col && (col.tipo === "inteiro" || col.tipo === "decimal");
      const dir = state.sortDir;
      positions.sort((a, b) => {
        const va = String(ROWS[a][state.sortCol] || "").trim();
        const vb = String(ROWS[b][state.sortCol] || "").trim();
        if (!va && !vb) return a - b;
        if (!va) return 1;
        if (!vb) return -1;
        if (isNum) {
          const na = parseNumeric(va);
          const nb = parseNumeric(vb);
          if (!Number.isNaN(na) && !Number.isNaN(nb)) {
            return na === nb ? a - b : (na < nb ? -1 : 1) * dir;
          }
        }
        const cmp = va.localeCompare(vb, "pt-BR", { numeric: true, sensitivity: "base" });
        return cmp === 0 ? a - b : cmp * dir;
      });
    }
    return positions;
  }

  function initHeader() {
    const titleEl = document.getElementById("hdr-title");
    titleEl.appendChild(el("span", { textContent: META.rotulo || "Pré-visualização" }));
    if (META.formato) {
      titleEl.appendChild(el("span", { className: "chip chip-accent", textContent: META.formato }));
    }
    document.getElementById("hdr-path").textContent = META.arquivo || "";

    const chips = document.getElementById("hdr-chips");
    const linhasLabel = META.total_linhas_fonte !== null && META.total_linhas_fonte !== undefined
      ? `${formatInt(ROWS.length)} de ${formatInt(META.total_linhas_fonte)}`
      : formatInt(ROWS.length);
    chips.appendChild(el("span", { className: "chip" }, [el("strong", { textContent: "Linhas:" }), ` ${linhasLabel}`]));
    chips.appendChild(el("span", { className: "chip" }, [el("strong", { textContent: "Colunas:" }), ` ${formatInt(COLS.length)}`]));
    if (META.modo_leitura === "amostra") {
      const sem = META.semente !== null && META.semente !== undefined ? ` (semente ${META.semente})` : "";
      chips.appendChild(el("span", { className: "chip", textContent: "Amostra uniforme" + sem }));
    } else if (META.pular > 0) {
      chips.appendChild(el("span", { className: "chip", textContent: `Pulando ${formatInt(META.pular)}` }));
    }
    if (META.tamanho_bytes) {
      chips.appendChild(el("span", { className: "chip" }, [el("strong", { textContent: "Tamanho:" }), ` ${formatBytes(META.tamanho_bytes)}`]));
    }
    if (META.encoding) {
      chips.appendChild(el("span", { className: "chip" }, [el("strong", { textContent: "Encoding:" }), ` ${META.encoding}`]));
    }
    if (META.separador) {
      chips.appendChild(el("span", { className: "chip" }, [el("strong", { textContent: "Separador:" }), ` ${META.separador}`]));
    }
    if (META.crs) {
      chips.appendChild(el("span", { className: "chip" }, [el("strong", { textContent: "CRS:" }), ` ${META.crs}`]));
    }
    if (META.tipo_geometria) {
      chips.appendChild(el("span", { className: "chip" }, [el("strong", { textContent: "Geometria:" }), ` ${META.tipo_geometria}`]));
    }
    if (HAS_DIC) {
      const comDic = COLS.filter((c) => c.descricao).length;
      chips.appendChild(el("span", { className: "chip chip-accent", textContent: `Dicionário INEP (${comDic} cols)` }));
      const sidePills = document.getElementById("side-pills");
      sidePills.appendChild(el("button", { className: "pill", "data-filter": "dicionario", type: "button", textContent: "Com dicionário" }));
    }
    if (HAS_DIC_CATS) {
      document.getElementById("wrap-dic-labels").style.display = "inline-flex";
      document.getElementById("wrap-v-dic").style.display = "inline-flex";
    }
    if (HAS_GEOM) {
      document.getElementById("schema-pills").appendChild(
        el("button", { className: "pill", "data-filter": "geometria", type: "button", textContent: "Geometria" })
      );
    }
  }

  function renderSidebar() {
    const listEl = document.getElementById("col-list");
    const cols = getSidebarCols();
    listEl.textContent = "";
    const frag = document.createDocumentFragment();
    for (const c of cols) {
      const cb = el("input", {
        type: "checkbox",
        checked: state.selected.has(c.idx),
        onChange: () => {
          if (cb.checked) state.selected.add(c.idx);
          else state.selected.delete(c.idx);
          renderAfterColSelection();
        }
      });
      const meta = el("div", { className: "col-item-meta" }, [
        el("div", { className: "col-item-name" }, [
          el("span", { className: "cname", textContent: `#${c.numero} ${c.nome}`, title: c.nome }),
          el("span", { className: "col-item-pct", textContent: `${c.pct_preenchidas}%` })
        ]),
        c.descricao ? el("div", { className: "col-item-desc", textContent: c.descricao, title: c.descricao }) : null
      ]);
      frag.appendChild(el("label", { className: "col-item" }, [cb, meta]));
    }
    listEl.appendChild(frag);
    document.getElementById("side-count").textContent = `${cols.length}/${COLS.length}`;
  }

  function renderTable() {
    const wrap = document.getElementById("table-scroll");
    const visCols = getVisibleCols();
    const rowPos = getFilteredSortedRowPositions();

    document.getElementById("table-status").textContent =
      `Mostrando ${formatInt(rowPos.length)} de ${formatInt(ROWS.length)} linhas · ${formatInt(visCols.length)} de ${formatInt(COLS.length)} colunas`;
    document.getElementById("global-status").textContent =
      `${formatInt(visCols.length)}/${formatInt(COLS.length)} colunas visíveis`;

    wrap.textContent = "";
    if (ROWS.length === 0) {
      wrap.appendChild(el("div", {
        className: "banner",
        textContent: "0 linhas carregadas (-n 0): exibindo apenas o esquema das colunas na aba Colunas (Esquema)."
      }));
      return;
    }
    if (visCols.length === 0) {
      wrap.appendChild(el("div", {
        className: "banner",
        textContent: "Nenhuma coluna visível. Marque colunas no painel lateral ou desmarque 'Ocultar colunas vazias'."
      }));
      return;
    }

    const table = el("table", { className: "data-grid" });
    const thead = el("thead");
    const trHead = el("tr");
    trHead.appendChild(el("th", { className: "rownum-col", textContent: "#" }));

    for (const c of visCols) {
      const tipParts = [`#${c.numero} ${c.nome} (${c.tipo}, ${c.pct_preenchidas}% preenchida)`];
      if (c.descricao) tipParts.push(c.descricao);
      if (c.categorias_texto) tipParts.push(c.categorias_texto);

      const ind = state.sortCol === c.idx ? (state.sortDir === 1 ? " ▲" : state.sortDir === -1 ? " ▼" : "") : "";
      const th = el("th", {
        title: tipParts.join("\n"),
        onClick: () => {
          if (state.sortCol !== c.idx) {
            state.sortCol = c.idx;
            state.sortDir = 1;
          } else {
            state.sortDir = state.sortDir === 1 ? -1 : state.sortDir === -1 ? 0 : 1;
            if (state.sortDir === 0) state.sortCol = null;
          }
          renderTable();
        }
      }, [
        el("span", { textContent: c.nome }),
        ind ? el("span", { className: "sort-ind", textContent: ind }) : null,
        c.descricao ? el("span", { className: "th-sub", textContent: c.descricao.slice(0, 42) + (c.descricao.length > 42 ? "..." : "") }) : null
      ]);
      trHead.appendChild(th);
    }
    thead.appendChild(trHead);
    table.appendChild(thead);

    const tbody = el("tbody");
    if (rowPos.length === 0) {
      tbody.appendChild(el("tr", null, [
        el("td", { colspan: visCols.length + 1, className: "cell-empty", textContent: "Nenhuma linha corresponde ao filtro." })
      ]));
    } else {
      for (const rIdx of rowPos) {
        const row = ROWS[rIdx];
        const lineNum = ROW_INDICES[rIdx] !== undefined ? ROW_INDICES[rIdx] : (rIdx + 1);
        const tr = el("tr");
        tr.appendChild(el("td", {
          className: "rownum-col",
          textContent: String(lineNum),
          title: "Abrir registro #" + lineNum + " na aba Vertical",
          onClick: () => {
            state.vPos = rIdx;
            switchTab("vertical");
          }
        }));
        for (const c of visCols) {
          const raw = row[c.idx] || "";
          const rot = state.showDicLabels && HAS_DIC_CATS ? getDicLabel(c, raw) : "";
          const display = raw === "" ? "(vazio)" : (rot ? `${raw} · ${rot}` : raw);
          tr.appendChild(el("td", {
            className: raw === "" ? "cell-empty" : "",
            textContent: display,
            title: raw === "" ? "(vazio)" : display,
            onClick: () => openCellModal(rIdx, c)
          }));
        }
        tbody.appendChild(tr);
      }
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
  }

  function renderSchema() {
    const wrap = document.getElementById("schema-scroll");
    const q = state.schemaQuery.trim().toLowerCase();
    const filtered = COLS.filter((c) => {
      if (state.schemaFilter === "preenchidas" && c.preenchidas === 0) return false;
      if (state.schemaFilter === "vazias" && c.preenchidas > 0) return false;
      if (state.schemaFilter === "numericas" && c.tipo !== "inteiro" && c.tipo !== "decimal") return false;
      if (state.schemaFilter === "texto" && c.tipo !== "texto") return false;
      if (state.schemaFilter === "geometria" && c.tipo !== "geometria") return false;
      if (q) {
        const hay = [
          c.nome, c.tipo, c.descricao || "", c.categorias_texto || "",
          ...(c.exemplos || [])
        ].join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    document.getElementById("schema-status").textContent = `${filtered.length} de ${COLS.length} colunas`;
    wrap.textContent = "";

    const table = el("table", { className: "schema-table" });
    const headRow = el("tr", null, [
      el("th", { textContent: "Visível", style: "width:54px;" }),
      el("th", { textContent: "#", style: "width:46px;" }),
      el("th", { textContent: "Coluna" }),
      el("th", { textContent: "Tipo" }),
      el("th", { textContent: "Preenchimento" }),
      el("th", { textContent: "Distintos" }),
      el("th", { textContent: "Top valores / Exemplos" }),
      HAS_DIC ? el("th", { textContent: "Dicionário (INEP)" }) : null
    ]);
    table.appendChild(el("thead", null, headRow));

    const tbody = el("tbody");
    for (const c of filtered) {
      const cb = el("input", {
        type: "checkbox",
        checked: state.selected.has(c.idx),
        onChange: () => {
          if (cb.checked) state.selected.add(c.idx);
          else state.selected.delete(c.idx);
          renderSidebar();
          renderTable();
        }
      });

      const exemplosCell = el("td");
      if (c.top_valores && c.top_valores.length) {
        for (const [val, cnt] of c.top_valores) {
          exemplosCell.appendChild(el("span", {
            className: "ex-chip",
            textContent: `${val} (${cnt})`,
            title: `${val} — ${cnt}x na amostra`
          }));
        }
      } else {
        exemplosCell.appendChild(el("span", { className: "cell-empty", textContent: "(sem valores)" }));
      }

      const dicCell = HAS_DIC ? el("td") : null;
      if (dicCell) {
        if (c.descricao) {
          dicCell.appendChild(el("div", { textContent: c.descricao }));
        }
        if (c.categorias_texto) {
          dicCell.appendChild(el("details", { className: "dic-cats" }, [
            el("summary", { textContent: "Categorias" }),
            el("pre", { textContent: c.categorias_texto })
          ]));
        }
        if (!c.descricao && !c.categorias_texto) {
          dicCell.appendChild(el("span", { className: "cell-empty", textContent: "-" }));
        }
      }

      tbody.appendChild(el("tr", null, [
        el("td", null, cb),
        el("td", { textContent: String(c.numero), style: "font-family:var(--mono);color:var(--text-muted);" }),
        el("td", { textContent: c.nome, style: "font-family:var(--mono);font-weight:600;" }),
        el("td", null, el("span", { className: `type-badge type-${c.tipo}`, textContent: c.tipo })),
        el("td", null, el("div", { className: "bar-wrap" }, [
          el("div", { className: "bar" }, el("div", { className: "bar-fill", style: `width:${c.pct_preenchidas}%` })),
          el("span", { style: "font-size:0.74rem;white-space:nowrap;", textContent: `${c.preenchidas}/${ROWS.length} (${c.pct_preenchidas}%)` })
        ])),
        el("td", { textContent: String(c.distintos) }),
        exemplosCell,
        dicCell
      ]));
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
  }

  function renderVertical() {
    const wrap = document.getElementById("vertical-scroll");
    const prevBtn = document.getElementById("btn-v-prev");
    const nextBtn = document.getElementById("btn-v-next");
    const posInput = document.getElementById("v-pos");
    const totalEl = document.getElementById("v-total");

    wrap.textContent = "";
    if (ROWS.length === 0) {
      prevBtn.disabled = true;
      nextBtn.disabled = true;
      posInput.value = 0;
      totalEl.textContent = "de 0";
      wrap.appendChild(el("div", {
        className: "banner",
        textContent: "0 linhas carregadas (-n 0): sem registros para exibir na visão vertical."
      }));
      return;
    }

    if (state.vPos < 0) state.vPos = 0;
    if (state.vPos >= ROWS.length) state.vPos = ROWS.length - 1;

    const row = ROWS[state.vPos];
    const lineNum = ROW_INDICES[state.vPos] !== undefined ? ROW_INDICES[state.vPos] : (state.vPos + 1);
    posInput.max = ROWS.length;
    posInput.value = state.vPos + 1;
    totalEl.textContent = `de ${formatInt(ROWS.length)} (linha #${formatInt(lineNum)} da fonte)`;
    prevBtn.disabled = state.vPos <= 0;
    nextBtn.disabled = state.vPos >= ROWS.length - 1;

    const q = state.vQuery.trim().toLowerCase();
    const card = el("div", { className: "vertical-card" });
    let count = 0;

    for (const c of COLS) {
      if (state.vOnlyChecked && !state.selected.has(c.idx)) continue;
      const raw = row[c.idx] || "";
      if (state.vHideEmpty && raw.trim() === "") continue;
      const rot = state.vShowDic && HAS_DIC_CATS ? getDicLabel(c, raw) : "";
      if (q) {
        const hay = (c.nome + " " + (c.descricao || "") + " " + raw + " " + rot).toLowerCase();
        if (!hay.includes(q)) continue;
      }
      count++;
      const keyEl = el("div", { className: "v-key" }, [
        `#${c.numero} ${c.nome}`,
        c.descricao ? el("span", { className: "v-key-desc", textContent: c.descricao }) : null
      ]);
      const valEl = el("div", { className: raw === "" ? "v-val empty" : "v-val" }, [
        raw === "" ? "(vazio)" : raw,
        rot ? el("span", { className: "dic-pill", textContent: rot }) : null
      ]);
      card.appendChild(el("div", { className: "v-row" }, [keyEl, valEl]));
    }

    if (count === 0) {
      wrap.appendChild(el("div", { className: "banner", textContent: "Nenhum campo corresponde aos filtros desta visão." }));
    } else {
      wrap.appendChild(card);
    }
  }

  function renderAfterColSelection() {
    renderSidebar();
    renderTable();
    if (state.tab === "colunas") renderSchema();
    if (state.tab === "vertical" && state.vOnlyChecked) renderVertical();
  }

  function switchTab(tabName) {
    state.tab = tabName;
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabName));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + tabName));
    if (tabName === "colunas") renderSchema();
    if (tabName === "vertical") renderVertical();
  }

  function openCellModal(rowPos, col) {
    const raw = ROWS[rowPos][col.idx] || "";
    const lineNum = ROW_INDICES[rowPos] !== undefined ? ROW_INDICES[rowPos] : (rowPos + 1);
    state.modalRowPos = rowPos;
    state.modalRawVal = raw;

    document.getElementById("modal-title").textContent = `${col.nome} (linha #${lineNum})`;
    document.getElementById("modal-meta").textContent =
      `Coluna #${col.numero} · Tipo aparente: ${col.tipo} · Preenchimento na amostra: ${col.pct_preenchidas}%`;
    document.getElementById("modal-val").textContent = raw === "" ? "(vazio)" : raw;

    const dicWrap = document.getElementById("modal-dic");
    dicWrap.textContent = "";
    if (col.descricao || col.categorias_texto) {
      if (col.descricao) dicWrap.appendChild(el("p", { style: "margin:0 0 0.35rem;" }, [el("strong", { textContent: "Descrição: " }), col.descricao]));
      const rot = getDicLabel(col, raw);
      if (rot) dicWrap.appendChild(el("p", { style: "margin:0 0 0.35rem;" }, [el("strong", { textContent: "Rótulo: " }), rot]));
      if (col.categorias_texto) dicWrap.appendChild(el("pre", { className: "modal-val", textContent: col.categorias_texto }));
    }
    document.getElementById("cell-modal").classList.add("open");
  }

  function closeModal() {
    document.getElementById("cell-modal").classList.remove("open");
  }

  function initTheme() {
    const btn = document.getElementById("btn-theme");
    let saved = "";
    try { saved = localStorage.getItem("georef_preview_theme") || ""; } catch (_e) {}
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    let theme = saved || (prefersDark ? "dark" : "light");

    function apply(t) {
      theme = t;
      document.documentElement.setAttribute("data-theme", t);
      btn.textContent = t === "dark" ? "Tema claro" : "Tema escuro";
      try { localStorage.setItem("georef_preview_theme", t); } catch (_e) {}
    }
    apply(theme);
    btn.addEventListener("click", () => apply(theme === "dark" ? "light" : "dark"));
  }

  function bindEvents() {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });

    let sideTimer;
    document.getElementById("side-search").addEventListener("input", (e) => {
      clearTimeout(sideTimer);
      sideTimer = setTimeout(() => { state.sideQuery = e.target.value; renderSidebar(); }, 100);
    });

    document.getElementById("side-pills").addEventListener("click", (e) => {
      const btn = e.target.closest(".pill");
      if (!btn) return;
      state.sideFilter = btn.dataset.filter;
      document.querySelectorAll("#side-pills .pill").forEach((p) => p.classList.toggle("active", p === btn));
      renderSidebar();
    });

    document.getElementById("btn-mark-filtered").addEventListener("click", () => {
      for (const c of getSidebarCols()) state.selected.add(c.idx);
      renderAfterColSelection();
    });
    document.getElementById("btn-unmark-filtered").addEventListener("click", () => {
      for (const c of getSidebarCols()) state.selected.delete(c.idx);
      renderAfterColSelection();
    });
    document.getElementById("btn-first-15").addEventListener("click", () => {
      state.selected = new Set(COLS.slice(0, 15).map((c) => c.idx));
      renderAfterColSelection();
    });
    document.getElementById("btn-mark-all").addEventListener("click", () => {
      state.selected = new Set(COLS.map((c) => c.idx));
      renderAfterColSelection();
    });

    const sidebar = document.getElementById("col-sidebar");
    const toggleBtn = document.getElementById("btn-toggle-sidebar");
    toggleBtn.addEventListener("click", () => {
      const collapsed = sidebar.classList.toggle("collapsed");
      toggleBtn.textContent = collapsed ? "Mostrar painel" : "Ocultar painel";
    });

    let rowTimer;
    document.getElementById("row-search").addEventListener("input", (e) => {
      clearTimeout(rowTimer);
      rowTimer = setTimeout(() => { state.rowQuery = e.target.value; renderTable(); }, 150);
    });

    document.getElementById("chk-hide-empty").addEventListener("change", (e) => {
      state.hideEmptyCols = e.target.checked;
      renderTable();
    });
    document.getElementById("chk-dic-labels").addEventListener("change", (e) => {
      state.showDicLabels = e.target.checked;
      renderTable();
    });
    document.getElementById("btn-copy-cols").addEventListener("click", () => {
      const nomes = getVisibleCols().map((c) => c.nome).join(",");
      if (!nomes) { showToast("Nenhuma coluna visível."); return; }
      copyText(nomes, "Nomes das colunas copiados.");
    });

    let schemaTimer;
    document.getElementById("schema-search").addEventListener("input", (e) => {
      clearTimeout(schemaTimer);
      schemaTimer = setTimeout(() => { state.schemaQuery = e.target.value; renderSchema(); }, 120);
    });
    document.getElementById("schema-pills").addEventListener("click", (e) => {
      const btn = e.target.closest(".pill");
      if (!btn) return;
      state.schemaFilter = btn.dataset.filter;
      document.querySelectorAll("#schema-pills .pill").forEach((p) => p.classList.toggle("active", p === btn));
      renderSchema();
    });

    document.getElementById("btn-v-prev").addEventListener("click", () => { state.vPos--; renderVertical(); });
    document.getElementById("btn-v-next").addEventListener("click", () => { state.vPos++; renderVertical(); });
    document.getElementById("v-pos").addEventListener("change", (e) => {
      const val = parseInt(e.target.value, 10);
      if (!Number.isNaN(val)) { state.vPos = val - 1; renderVertical(); }
    });
    let vTimer;
    document.getElementById("v-search").addEventListener("input", (e) => {
      clearTimeout(vTimer);
      vTimer = setTimeout(() => { state.vQuery = e.target.value; renderVertical(); }, 120);
    });
    document.getElementById("v-hide-empty").addEventListener("change", (e) => { state.vHideEmpty = e.target.checked; renderVertical(); });
    document.getElementById("v-only-checked").addEventListener("change", (e) => { state.vOnlyChecked = e.target.checked; renderVertical(); });
    document.getElementById("v-dic-labels").addEventListener("change", (e) => { state.vShowDic = e.target.checked; renderVertical(); });

    document.getElementById("modal-close").addEventListener("click", closeModal);
    document.getElementById("cell-modal").addEventListener("click", (e) => {
      if (e.target.id === "cell-modal") closeModal();
    });
    document.getElementById("modal-copy").addEventListener("click", () => copyText(state.modalRawVal, "Valor copiado."));
    document.getElementById("modal-open-vertical").addEventListener("click", () => {
      state.vPos = state.modalRowPos;
      closeModal();
      switchTab("vertical");
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeModal();
    });
  }

  initTheme();
  initHeader();
  bindEvents();
  renderSidebar();
  renderTable();
})();
</script>
</body>
</html>
"""


def _escapar_html_texto(texto):
    """Escapa texto para uso em elementos HTML como <title>."""
    return (
        str(texto)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def gerar_html(payload):
    """Serializa payload em JSON seguro e injeta no template HTML auto-contido."""
    json_seguro = (
        json.dumps(payload, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    titulo = f"Pré-visualização — {payload['meta'].get('rotulo') or 'Dataset'}"
    subst = {
        "__TITULO__": _escapar_html_texto(titulo),
        "__JSON_DADOS__": json_seguro,
    }
    return re.sub(r"__TITULO__|__JSON_DADOS__", lambda m: subst[m.group(0)], TEMPLATE_HTML)


# ------------------------------------------------------------------------ CLI

def montar_argumentos():
    """Define os argumentos da linha de comando."""
    p = argparse.ArgumentParser(
        description="Gera uma pré-visualização visual (HTML interativo offline) das colunas e de um recorte limitado de linhas de qualquer conjunto de dados.",
        epilog="Exemplos: veja o cabeçalho do script (" + Path(__file__).name + ").",
    )
    p.add_argument("arquivo", help="caminho do arquivo (CSV, TSV, ZIP, GPKG, GeoJSON, SHP, XLSX, JSON/JSONL)")
    p.add_argument("-n", "--linhas", type=int, default=50, help="número máximo de linhas a pré-visualizar (padrão: %(default)s)")
    p.add_argument("--pular", type=int, default=0, help="ignorar as primeiras N linhas/feições antes de carregar (padrão: %(default)s)")
    p.add_argument("--amostra", action="store_true", help="sortear N linhas aleatórias uniformemente em vez das primeiras")
    p.add_argument("--semente", type=int, help="semente do sorteio aleatório quando usado com --amostra")
    p.add_argument("-t", "--tabela", help="nome da tabela no ZIP, camada no GeoPackage ou aba no .xlsx")
    p.add_argument("--listar", action="store_true", help="lista as tabelas/camadas/abas disponíveis e sai")
    p.add_argument("--colunas", help="carregar apenas estas colunas (separadas por vírgula)")
    p.add_argument("--filtro-colunas", help="manter apenas colunas cujo nome ou descrição contém este texto")
    p.add_argument("--sep", help="forçar separador do CSV (ex.: ';' ou ',')")
    p.add_argument("--encoding", help="forçar codificação do arquivo (ex.: utf-8-sig, latin-1)")
    p.add_argument("--sem-geometria", action="store_true", help="omitir coluna de geometria em bases geoespaciais")
    p.add_argument("-o", "--saida", help="caminho do HTML gerado (padrão: temp/preview_<nome>.html)")
    p.add_argument("--nao-abrir", action="store_true", help="não abrir o HTML automaticamente no navegador")
    return p


def caminho_saida_padrao(meta):
    """Define temp/preview_<nome>.html baseado no arquivo e tabela/camada."""
    caminho = Path(meta["arquivo"])
    base = caminho.stem
    if meta.get("tabela") and meta["tabela"].lower() not in base.lower():
        base = f"{base}__{meta['tabela']}"
    return PASTA_TEMP / f"preview_{slug_seguro(base)}.html"


def principal():
    """Ponto de entrada CLI."""
    inicio = time.time()
    args = montar_argumentos().parse_args()
    if args.linhas < 0:
        sair("-n/--linhas não pode ser negativo.")
    if args.pular < 0:
        sair("--pular não pode ser negativo.")

    df, indices_linhas, meta, dicionario = carregar_dados(args)
    df = aplicar_selecao_colunas(df, args, dicionario)

    perfis = analisar_colunas(df, dicionario, geom_col=meta.get("geom_col"))
    linhas_matriz = [[valor_para_texto(v) for v in row] for row in df.itertuples(index=False, name=None)]

    payload = {
        "meta": meta,
        "colunas": perfis,
        "linhas": linhas_matriz,
        "indices_linhas": indices_linhas,
    }

    html = gerar_html(payload)
    destino = Path(args.saida) if args.saida else caminho_saida_padrao(meta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")

    duracao = time.time() - inicio
    total_txt = f" / {formatar_milhar(meta['total_linhas_fonte'])}" if meta.get("total_linhas_fonte") is not None else ""
    print(f"Fonte:   {meta['rotulo']} [{meta['formato']}]")
    print(f"Recorte: {formatar_milhar(len(linhas_matriz))}{total_txt} linha(s) x {formatar_milhar(len(perfis))} coluna(s)")
    if meta.get("separador"):
        print(f"CSV:     encoding={meta['encoding']}, sep='{meta['separador']}'")
    elif meta.get("encoding"):
        print(f"Leitura: encoding={meta['encoding']}")
    if meta.get("crs"):
        print(f"Geo:     CRS={meta['crs']}, geometria={meta.get('tipo_geometria') or '-'}")
    if dicionario:
        com_dic = sum(1 for c in perfis if c.get("descricao"))
        print(f"Dicion.: {com_dic} de {len(perfis)} coluna(s) com descrição do INEP")
    print(f"HTML:    {destino} ({formatar_bytes(destino.stat().st_size)}) em {duracao:.2f}s")

    if not args.nao_abrir:
        webbrowser.open(destino.resolve().as_uri())


if __name__ == "__main__":
    principal()
