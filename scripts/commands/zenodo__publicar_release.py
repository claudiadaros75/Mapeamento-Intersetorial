#!/usr/bin/env python3
"""Publica uma release no Zenodo pela API e obtem o DOI.

Faz parte do fluxo de ciencia aberta descrito no README.org ("Registro e
divulgacao do processo colaborativo") e e chamado pelo workflow
.github/workflows/zenodo-release.yml.

Na primeira publicacao cria um registro novo no Zenodo.  Nas seguintes,
se ZENODO_CONCEPT_RECID estiver definido, cria uma *nova versao* do mesmo
registro: cada release tem seu proprio DOI, e o "DOI conceito" aponta
sempre para a versao mais recente.

Os metadados (titulo, autores, licenca, palavras-chave) vem do arquivo
.zenodo.json na raiz do repositorio; a versao, a data e as notas da
release sao acrescentadas aqui.

Variaveis de ambiente:
    ZENODO_TOKEN           token pessoal do Zenodo (escopos deposit:write e
                           deposit:actions)
    ZENODO_CONCEPT_RECID   (opcional) id do registro conceito, para criar
                           uma nova versao em vez de um registro novo
    GITHUB_OUTPUT          (opcional) recebe doi, concept_doi, concept_recid
                           e url, para os passos seguintes do workflow

Uso:
    python3 scripts/commands/zenodo__publicar_release.py --sandbox \\
        --versao v0.1.0 --notas notas.md --arquivo codigo.zip --arquivo auditoria.zip

Use --sandbox (sandbox.zenodo.org, com token proprio) para testar: os DOIs
do sandbox sao ficticios.  Usa apenas a biblioteca padrao.
"""

import argparse
import datetime
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent


def requisitar(metodo, url, token, dados=None, arquivo=None):
    """Faz uma requisicao a API do Zenodo e devolve o JSON da resposta."""
    req = urllib.request.Request(url, method=metodo)
    req.add_header("Authorization", f"Bearer {token}")
    corpo = None
    if arquivo is not None:
        req.add_header("Content-Type", "application/octet-stream")
        req.add_header("Content-Length", str(arquivo.stat().st_size))
        corpo = arquivo.open("rb")
    elif dados is not None:
        req.add_header("Content-Type", "application/json")
        corpo = json.dumps(dados).encode()
    try:
        with urllib.request.urlopen(req, data=corpo, timeout=600) as resp:
            texto = resp.read()
    except urllib.error.HTTPError as erro:
        sys.exit(f"Zenodo respondeu {erro.code} em {metodo} {url}:\n{erro.read().decode()}")
    finally:
        if arquivo is not None:
            corpo.close()
    return json.loads(texto) if texto else {}


def carregar_metadados(caminho, sandbox):
    metadados = json.loads(caminho.read_text(encoding="utf-8"))
    for autor in metadados.get("creators", []):
        if "Sobrenome" in autor.get("name", ""):
            aviso = f"Preencha os autores reais em {caminho} (campo creators)"
            if not sandbox:
                sys.exit(f"{aviso} antes de publicar.")
            print(f"AVISO: {aviso}; aceito apenas no sandbox.")
    return metadados


def descricao_com_notas(descricao, notas, versao):
    """Acrescenta as notas da release (Markdown) a descricao em HTML do Zenodo."""
    if not notas.strip():
        return descricao
    return (f"{descricao}<h3>Notas da release {html.escape(versao)}</h3>"
            f"<pre>{html.escape(notas.strip())}</pre>")


def preparar_rascunho(api, token, concept_recid):
    """Cria um rascunho novo ou uma nova versao do registro conceito."""
    if not concept_recid:
        print("Criando um registro novo no Zenodo...")
        return requisitar("POST", f"{api}/deposit/depositions", token, dados={})

    ultimo = requisitar("GET", f"{api}/records/{concept_recid}/versions/latest", token)
    print(f"Criando nova versão a partir do registro {ultimo['id']}...")
    resposta = requisitar(
        "POST", f"{api}/deposit/depositions/{ultimo['id']}/actions/newversion", token)
    rascunho = requisitar("GET", resposta["links"]["latest_draft"], token)
    # A nova versao herda os arquivos da anterior; eles sao trocados pelos novos.
    for arquivo in rascunho.get("files", []):
        requisitar("DELETE",
                   f"{api}/deposit/depositions/{rascunho['id']}/files/{arquivo['id']}", token)
    return rascunho


def gravar_saidas(saidas):
    destino = os.environ.get("GITHUB_OUTPUT")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            for chave, valor in saidas.items():
                f.write(f"{chave}={valor}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--versao", required=True, help="tag da release (ex.: v0.1.0)")
    parser.add_argument("--arquivo", type=Path, action="append", required=True,
                        help="arquivo a depositar (pode repetir)")
    parser.add_argument("--notas", type=Path, help="notas da release em Markdown")
    parser.add_argument("--metadados", type=Path, default=RAIZ / ".zenodo.json")
    parser.add_argument("--sandbox", action="store_true",
                        help="usar sandbox.zenodo.org (DOIs ficticios, para teste)")
    args = parser.parse_args()

    token = os.environ.get("ZENODO_TOKEN")
    if not token:
        sys.exit("Defina ZENODO_TOKEN com um token pessoal do Zenodo.")
    api = "https://sandbox.zenodo.org/api" if args.sandbox else "https://zenodo.org/api"

    metadados = carregar_metadados(args.metadados, args.sandbox)
    notas = args.notas.read_text(encoding="utf-8") if args.notas else ""
    metadados["version"] = args.versao
    metadados["publication_date"] = datetime.date.today().isoformat()
    metadados["description"] = descricao_com_notas(
        metadados.get("description", ""), notas, args.versao)

    rascunho = preparar_rascunho(api, token, os.environ.get("ZENODO_CONCEPT_RECID"))
    bucket = rascunho["links"]["bucket"]
    for arquivo in args.arquivo:
        print(f"Enviando {arquivo.name} ({arquivo.stat().st_size / 1e6:.1f} MB)...")
        requisitar("PUT", f"{bucket}/{urllib.parse.quote(arquivo.name)}", token, arquivo=arquivo)

    requisitar("PUT", f"{api}/deposit/depositions/{rascunho['id']}", token,
               dados={"metadata": metadados})
    publicado = requisitar(
        "POST", f"{api}/deposit/depositions/{rascunho['id']}/actions/publish", token)

    saidas = {
        "doi": publicado["doi"],
        "concept_doi": publicado.get("conceptdoi", ""),
        "concept_recid": publicado.get("conceptrecid", ""),
        "url": publicado["links"].get("record_html") or publicado["links"].get("html", ""),
    }
    gravar_saidas(saidas)
    for chave, valor in saidas.items():
        print(f"{chave}: {valor}")


if __name__ == "__main__":
    main()
