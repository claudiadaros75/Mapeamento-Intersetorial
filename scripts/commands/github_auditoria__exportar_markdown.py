#!/usr/bin/env python3
"""Exporta a trilha de auditoria do repositorio no GitHub para Markdown.

Faz parte do fluxo de ciencia aberta descrito no README.org ("Registro e
divulgacao do processo colaborativo"): a cada release, o workflow
.github/workflows/zenodo-release.yml roda este script e o resultado vai
junto com o codigo para o Zenodo, sob o DOI da release.

O que e exportado (para a pasta de saida):
    README.md                indice geral
    issues/NNNN-titulo.md    cada issue: metadados, descricao e linha do tempo
                             completa (comentarios, rotulos, milestones,
                             referencias cruzadas, fechamento...)
    pull-requests/NNNN-...   cada PR: o mesmo das issues, mais revisoes,
                             comentarios em linhas de codigo e commits
    milestones.md            fases do projeto
    releases.md              releases anteriores e suas notas
    historico-commits.md     git log completo ate a tag (requer clone completo)
    json/                    respostas brutas da API do GitHub, sem perdas
    SHA256SUMS               hash de cada arquivo exportado

Uso:
    GITHUB_TOKEN=... python3 scripts/commands/github_auditoria__exportar_markdown.py \\
        --repo claudiadaros75/Mapeamento-Intersetorial --tag v0.1.0 --saida build/auditoria

Sem GITHUB_TOKEN a API do GitHub limita a 60 requisicoes por hora, o que so
basta para repositorios muito pequenos.  Usa apenas a biblioteca padrao.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

API = "https://api.github.com"


def api_get(caminho, token):
    """GET na API do GitHub, seguindo a paginacao (cabecalho Link)."""
    url = caminho if caminho.startswith("http") else f"{API}{caminho}"
    resultados = []
    while url:
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=60) as resp:
            dados = json.load(resp)
            link = resp.headers.get("Link", "")
        if not isinstance(dados, list):
            return dados
        resultados.extend(dados)
        proximo = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = proximo.group(1) if proximo else None
    return resultados


def com_paginacao(caminho):
    separador = "&" if "?" in caminho else "?"
    return f"{caminho}{separador}per_page=100"


def slug(texto, limite=60):
    texto = re.sub(r"[^\w\s-]", "", texto.lower(), flags=re.UNICODE)
    return re.sub(r"[\s_-]+", "-", texto).strip("-")[:limite] or "sem-titulo"


def citar(texto):
    """Coloca um texto Markdown em bloco de citacao, preservando a estrutura."""
    if not texto or not texto.strip():
        return "> *(sem texto)*"
    return "\n".join(f"> {linha}" if linha else ">" for linha in texto.strip().splitlines())


def login(usuario):
    return f"@{usuario['login']}" if usuario else "(usuario removido)"


def data(valor):
    return valor.replace("T", " ").replace("Z", " UTC") if valor else "—"


def evento_md(ev):
    """Converte um evento da timeline da API em uma entrada Markdown."""
    tipo = ev.get("event")
    quem = login(ev.get("actor") or ev.get("user"))
    quando = data(ev.get("created_at") or ev.get("submitted_at"))

    if tipo == "commented":
        return f"#### Comentário de {quem} em {quando}\n\n{citar(ev.get('body'))}\n"
    if tipo == "reviewed":
        estado = ev.get("state", "").lower()
        return (f"#### Revisão de {quem} em {quando} — {estado}\n\n"
                f"{citar(ev.get('body'))}\n")
    if tipo == "committed":
        autor = ev.get("author", {})
        msg = (ev.get("message") or "").splitlines()[0]
        return (f"- {data(autor.get('date'))} — commit `{ev.get('sha', '')[:7]}` "
                f"de {autor.get('name', '?')}: {msg}")
    if tipo in ("labeled", "unlabeled"):
        acao = "adicionou" if tipo == "labeled" else "removeu"
        return f"- {quando} — {quem} {acao} o rótulo `{ev['label']['name']}`"
    if tipo in ("milestoned", "demilestoned"):
        acao = "associou à" if tipo == "milestoned" else "retirou da"
        return f"- {quando} — {quem} {acao} milestone *{ev['milestone']['title']}*"
    if tipo == "renamed":
        r = ev.get("rename", {})
        return f"- {quando} — {quem} renomeou de “{r.get('from')}” para “{r.get('to')}”"
    if tipo == "cross-referenced":
        origem = ev.get("source", {}).get("issue", {})
        return (f"- {quando} — referenciado em #{origem.get('number')} "
                f"({origem.get('title', '')})")
    if tipo in ("closed", "merged", "referenced") and ev.get("commit_id"):
        return f"- {quando} — {quem}: {tipo} (commit `{ev['commit_id'][:7]}`)"
    if tipo in ("assigned", "unassigned"):
        return f"- {quando} — {quem}: {tipo} {login(ev.get('assignee'))}"
    return f"- {quando} — {quem}: {tipo}"


def exportar_item(repo, item, token, pasta, pasta_json):
    """Gera o Markdown (e o JSON bruto) de uma issue ou PR."""
    numero = item["number"]
    eh_pr = "pull_request" in item
    bruto = {"item": item}

    bruto["timeline"] = api_get(com_paginacao(f"/repos/{repo}/issues/{numero}/timeline"), token)
    if eh_pr:
        bruto["pull"] = api_get(f"/repos/{repo}/pulls/{numero}", token)
        bruto["review_comments"] = api_get(
            com_paginacao(f"/repos/{repo}/pulls/{numero}/comments"), token)

    linhas = [f"# {'PR' if eh_pr else 'Issue'} #{numero}: {item['title']}", ""]
    linhas += [
        f"- **Autor**: {login(item['user'])}",
        f"- **Estado**: {item['state']}",
        f"- **Criado em**: {data(item['created_at'])}",
        f"- **Fechado em**: {data(item.get('closed_at'))}",
        f"- **Rótulos**: {', '.join(l['name'] for l in item['labels']) or '—'}",
        f"- **Milestone**: {(item.get('milestone') or {}).get('title', '—')}",
        f"- **Endereço**: {item['html_url']}",
    ]
    if eh_pr:
        pr = bruto["pull"]
        linhas += [
            f"- **Branch**: `{pr['head']['ref']}` → `{pr['base']['ref']}`",
            f"- **Integrado em**: {data(pr.get('merged_at'))}"
            + (f" por {login(pr.get('merged_by'))}" if pr.get("merged_by") else ""),
            f"- **Commit de integração**: `{pr.get('merge_commit_sha') or '—'}`",
        ]
    linhas += ["", "## Descrição", "", citar(item.get("body")), "", "## Linha do tempo", ""]
    for ev in bruto["timeline"]:
        entrada = evento_md(ev)
        if entrada.startswith("#"):  # comentarios e revisoes viram blocos
            linhas.append("")
        linhas.append(entrada)

    if eh_pr and bruto["review_comments"]:
        linhas += ["", "## Comentários em linhas de código", ""]
        for c in bruto["review_comments"]:
            linhas += [
                f"#### {login(c['user'])} em {data(c['created_at'])} — "
                f"`{c['path']}` (linha {c.get('line') or c.get('original_line')})",
                "", "```diff", c.get("diff_hunk", ""), "```", "", citar(c.get("body")), "",
            ]

    nome = f"{numero:04d}-{slug(item['title'])}"
    (pasta / f"{nome}.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    (pasta_json / f"{'pr' if eh_pr else 'issue'}-{numero:04d}.json").write_text(
        json.dumps(bruto, ensure_ascii=False, indent=2), encoding="utf-8")
    return nome


def exportar_milestones(repo, token, saida):
    milestones = api_get(com_paginacao(f"/repos/{repo}/milestones?state=all"), token)
    linhas = ["# Milestones (fases do projeto)", ""]
    for m in milestones:
        linhas += [
            f"## {m['title']}", "",
            f"- **Estado**: {m['state']} — {m['closed_issues']} itens fechados, "
            f"{m['open_issues']} abertos",
            f"- **Prazo**: {data(m.get('due_on'))}",
            f"- **Fechada em**: {data(m.get('closed_at'))}",
            "", citar(m.get("description")), "",
        ]
    if not milestones:
        linhas.append("*Nenhuma milestone cadastrada.*")
    (saida / "milestones.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return milestones


def exportar_releases(repo, token, saida):
    releases = api_get(com_paginacao(f"/repos/{repo}/releases"), token)
    linhas = ["# Releases", ""]
    for r in releases:
        linhas += [
            f"## {r.get('name') or r['tag_name']} (`{r['tag_name']}`)", "",
            f"- **Publicada em**: {data(r.get('published_at'))} por {login(r.get('author'))}",
            f"- **Endereço**: {r['html_url']}",
            "", citar(r.get("body")), "",
        ]
    if not releases:
        linhas.append("*Nenhuma release publicada.*")
    (saida / "releases.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return releases


def exportar_commits(tag, saida):
    """Historico do git ate a tag; exige um clone completo (fetch-depth: 0)."""
    formato = "- %ad — `%h` — %an: %s"
    try:
        log = subprocess.run(
            ["git", "log", "--date=iso-strict", f"--format={formato}", tag],
            check=True, capture_output=True, text=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as erro:
        log = f"*Não foi possível ler o histórico do git: {erro}*\n"
    texto = f"# Histórico de commits até `{tag}`\n\n{log}"
    (saida / "historico-commits.md").write_text(texto, encoding="utf-8")


def gravar_sha256sums(saida):
    linhas = []
    for arquivo in sorted(p for p in saida.rglob("*") if p.is_file()):
        if arquivo.name == "SHA256SUMS":
            continue
        digest = hashlib.sha256(arquivo.read_bytes()).hexdigest()
        linhas.append(f"{digest}  {arquivo.relative_to(saida).as_posix()}")
    (saida / "SHA256SUMS").write_text("\n".join(linhas) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"),
                        help="dono/repositorio (padrao: $GITHUB_REPOSITORY)")
    parser.add_argument("--tag", required=True, help="tag da release (ex.: v0.1.0)")
    parser.add_argument("--saida", type=Path, default=Path("build/auditoria"))
    args = parser.parse_args()
    if not args.repo:
        parser.error("informe --repo ou defina GITHUB_REPOSITORY")

    token = os.environ.get("GITHUB_TOKEN")
    saida = args.saida
    pastas = {nome: saida / nome for nome in ("issues", "pull-requests", "json")}
    for pasta in pastas.values():
        pasta.mkdir(parents=True, exist_ok=True)

    itens = api_get(com_paginacao(f"/repos/{args.repo}/issues?state=all&direction=asc"), token)
    issues, prs = [], []
    for item in itens:
        eh_pr = "pull_request" in item
        pasta = pastas["pull-requests"] if eh_pr else pastas["issues"]
        nome = exportar_item(args.repo, item, token, pasta, pastas["json"])
        (prs if eh_pr else issues).append((item, nome))
        print(f"{'PR' if eh_pr else 'Issue'} #{item['number']}: {item['title']}")

    milestones = exportar_milestones(args.repo, token, saida)
    releases = exportar_releases(args.repo, token, saida)
    exportar_commits(args.tag, saida)

    agora = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    indice = [
        f"# Trilha de auditoria — {args.repo} — `{args.tag}`", "",
        f"Exportada em {agora} a partir da API do GitHub, para arquivamento",
        "junto com a release no Zenodo.  A pasta `json/` guarda as respostas",
        "brutas da API, sem perdas; `SHA256SUMS` permite conferir a",
        "integridade de cada arquivo (`sha256sum -c SHA256SUMS`).", "",
        "Imagens e anexos citados nos textos aparecem apenas como links.", "",
        f"- [Milestones](milestones.md) ({len(milestones)})",
        f"- [Releases](releases.md) ({len(releases)})",
        "- [Histórico de commits](historico-commits.md)", "",
        f"## Issues ({len(issues)})", "",
    ]
    indice += [f"- [#{i['number']} {i['title']}](issues/{n}.md) — {i['state']}"
               for i, n in issues] or ["*Nenhuma issue.*"]
    indice += ["", f"## Pull Requests ({len(prs)})", ""]
    indice += [f"- [#{p['number']} {p['title']}](pull-requests/{n}.md) — {p['state']}"
               for p, n in prs] or ["*Nenhum pull request.*"]
    (saida / "README.md").write_text("\n".join(indice) + "\n", encoding="utf-8")

    gravar_sha256sums(saida)
    print(f"Trilha de auditoria gravada em {saida}/")


if __name__ == "__main__":
    main()
