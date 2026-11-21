# Organizar `scripts/` em `commands/` e `utils/`

## Goal

Separar, dentro de `scripts/`, os **comandos do pipeline** (etapas que baixam,
juntam, cruzam, georreferenciam e geram os dados do projeto) dos **utilitários**
(biblioteca compartilhada, ferramentas de inspeção de dados e scripts de
publicação/manutenção), para que fique claro o que é uma etapa do fluxo de
dados e o que é apoio.

## Scope

- `scripts/commands/`: só as etapas do pipeline.
- `scripts/utils/` (novo): biblioteca + teste, ferramentas de inspeção,
  publicação (docs, GitHub, Zenodo) e o arquivo do restclient.
- Atualizar todas as referências (imports, README, docs, workflow, `init.el`).
- Fora do escopo: mudar o comportamento dos scripts; regerar `web/docs/*.html`.

## Classificação

| Pasta | Arquivos |
|---|---|
| `commands/` | `catalogo_censo_2025__comparar`, `censo_escolar_2025__cruzar_catalogo`, `censo_escolar_2025__georreferenciar`, `escolas_dados__cruzar_censo_2025_cnefe`, `escolas_dados__cruzar_inep_cnefe`, `escolas__gerar_dados_mapa`, `escolas__gerar_dados_mapa_nacional`, `escolas_mapa__gerar_dados_auditoria`, `escolas_mapa__gerar_dados_web`, `escolas__parear_inep_cnefe`, `ibge_cnefe__baixar_dados`, `ibge_cnefe__extrair_escolas`, `ibge_malha_municipal__baixar_dados_formato_geojson`, `ibge_malha_municipal__baixar_dados_formato_shapefile`, `inep_cadastro_escolar__juntar_exportacoes`, `inep_catalogo_escolas__baixar_dados`, `inep_censo_escolar__baixar_dados`, `inep_censo_escolar__juntar_cadastro_escolar` |
| `utils/` — biblioteca | `escolas_normalizacao.py`, `test_escolas_normalizacao.py` |
| `utils/` — inspeção | `explorardados.py`, `previsualizar_dados.py`, `ibge_malha_municipal__explorar_shapefiles.py`, `restclient-ibge-malhas-api.http` |
| `utils/` — publicação | `exportar_docs_org_para_html.sh`, `github_auditoria__exportar_markdown.py`, `zenodo__publicar_release.py` |

Os comandos que importam outros comandos (por exemplo, `escolas__parear_inep_cnefe`
importado por `escolas__gerar_dados_mapa`) continuam em `commands/`, porque
também são etapas executáveis do pipeline.

## Task Breakdown

1. **Mover os arquivos com `git mv`.** *Justificativa:* preserva o histórico
   de cada arquivo (`git log --follow`).
2. **Eliminar o `.http` duplicado.** *Justificativa:* `scripts/restclient-ibge-malhas-api.http`
   e `scripts/commands/restclient-ibge-malhas-api.http` eram idênticos; ter
   uma cópia só evita que divirjam.
3. **Pôr `scripts/utils` no `sys.path` dos comandos que importam `escolas_normalizacao`.**
   *Justificativa:* sem isso, `escolas__parear_inep_cnefe` e
   `censo_escolar_2025__georreferenciar` (e, por tabela, `escolas__gerar_dados_mapa`)
   quebram com `ModuleNotFoundError`.
4. **Atualizar referências em README.org, docs, workflow do Zenodo e docstrings.**
   *Justificativa:* o workflow `.github/workflows/zenodo-release.yml` chama
   os scripts de publicação pelo caminho; um caminho antigo quebraria a release.
5. **Ajustar o `init.el` (`georef/rodar-script`, menu e atalhos).**
   *Justificativa:* o menu Georef listava só `scripts/commands/`, então os
   utilitários deixariam de aparecer.
6. **Verificar.** *Justificativa:* confirmar que nada quebrou com a mudança.

## What Was Done

- **Tarefas 1 e 2:** 8 arquivos movidos para `scripts/utils/`; `.http` da raiz de
  `scripts/` movido para `utils/` e a cópia em `commands/` removida.
- **Tarefa 3:** linha `sys.path.insert(0, .../"utils")` adicionada em
  `scripts/commands/escolas__parear_inep_cnefe.py` e
  `scripts/commands/censo_escolar_2025__georreferenciar.py`.
- **Tarefa 4:** `sed` em `README.org`, `.github/workflows/zenodo-release.yml`,
  `docs/01-…`, `docs/03-…`, `docs/features/*` e nas docstrings dos scripts movidos.
- **Tarefa 5:** `georef/rodar-script` agora lista `commands/*.py` e `utils/*.py`.
- **Tarefa 6 (verificação):**
  - `.venv/bin/python -m unittest scripts/utils/test_escolas_normalizacao.py` → `Ran 26 tests … OK`
  - `emacs --batch … (check-parens)` em `init.el` → `parens OK`
  - `bash -n scripts/utils/exportar_docs_org_para_html.sh` → OK
  - Import de `escolas__parear_inep_cnefe`, `censo_escolar_2025__georreferenciar`
    e `escolas__gerar_dados_mapa` (com um `rapidfuzz` falso, pois ele não está
    instalado no `.venv`) → `nz` resolvido para `scripts/utils/escolas_normalizacao.py`.
  - `--help` dos demais scripts OK.
- **Pendências conhecidas (não causadas por esta mudança):** o `.venv` não tem
  `rapidfuzz`, embora ele esteja em `requirements.txt` (`pip install -r requirements.txt` resolve); `web/docs/*.html` ainda mostram
  os caminhos antigos até a próxima execução de `exportar_docs_org_para_html.sh`.
