#!/usr/bin/env bash
# ==============================================================================
# exportar_docs_org_para_html.sh
#
# Exporta todos os arquivos de documentação Org-mode (.org) para páginas
# HTML estáticas na pasta web/docs/, prontas para publicação web (GitHub Pages).
#
# Uso:
#   ./scripts/commands/exportar_docs_org_para_html.sh
# ==============================================================================

set -euo pipefail

# Diretório raiz do projeto
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DOCS_SRC_DIR="${ROOT_DIR}/docs"
DOCS_DEST_DIR="${ROOT_DIR}/web/docs"

echo "========================================================================"
echo "📚 Exportando Documentação Org-mode para HTML Estático"
echo "========================================================================"
echo "Origem:  ${DOCS_SRC_DIR}"
echo "Destino: ${DOCS_DEST_DIR}"
echo ""

# Cria o diretório de destino web/docs/ se não existir
mkdir -p "${DOCS_DEST_DIR}"

# Verifica se o Emacs está instalado
if ! command -v emacs &> /dev/null; then
    echo "❌ Erro: Emacs não encontrado no sistema. Instale o Emacs para continuar." >&2
    exit 1
fi

EMACS_VERSION=$(emacs --version | head -n 1)
echo "Utilizando: ${EMACS_VERSION}"
echo ""

# Script Elisp para exportação customizada com visual moderno
ELISP_EXPORT_CONFIG=$(cat << 'EOF'
(require 'org)
(require 'ox-html)

;; Configurações de exportação HTML do Org-mode
(setq org-html-htmlize-output-type nil)
(setq org-html-doctype "html5")
(setq org-html-html5-fancy t)
(setq org-html-link-org-files-as-html t)
(setq org-html-validation-link nil)
(setq org-html-head-include-default-style nil)
(setq org-html-head-include-scripts nil)

;; Injeta a folha de estilos personalizada
(setq org-html-head "
<link rel=\"stylesheet\" href=\"../css/style.css\">
<link rel=\"stylesheet\" href=\"../css/docs.css\">
")

;; Cabeçalho de navegação no topo de cada documento
(setq org-html-preamble "
<header class=\"app-header\">
  <div class=\"header-title\">
    <a href=\"../index.html\" class=\"btn-home-link\" title=\"Voltar ao Portal de Mapas\">🏠 Início</a>
    <a href=\"../ibge_malhas.html\" class=\"btn-home-link\" title=\"Abrir Mapa Interativo\">🗺️ Mapa</a>
    <h1>📚 Documentação do Projeto</h1>
  </div>
</header>
<div class=\"doc-page-container\">
")

;; Rodapé de fechamento
(setq org-html-postamble "
</div>
<footer class=\"footer\">
  <p>Projeto de Georreferenciamento &bull; Malhas do IBGE 2024 &bull; <a href=\"../index.html\">Voltar ao Portal</a></p>
</footer>
")
EOF
)

# Exporta cada arquivo .org de docs/
COUNT=0
for org_file in "${DOCS_SRC_DIR}"/*.org; do
    if [ -f "${org_file}" ]; then
        filename=$(basename "${org_file}")
        basename_no_ext="${filename%.*}"
        dest_html="${DOCS_DEST_DIR}/${basename_no_ext}.html"

        echo "  📄 Exportando: docs/${filename} -> web/docs/${basename_no_ext}.html"

        emacs -Q --batch \
            --eval "${ELISP_EXPORT_CONFIG}" \
            --visit "${org_file}" \
            --eval "(org-html-export-to-html)" \
            2>&1 | sed 's/^/     /'

        # Move o arquivo .html gerado ao lado do .org para web/docs/
        if [ -f "${DOCS_SRC_DIR}/${basename_no_ext}.html" ]; then
            mv "${DOCS_SRC_DIR}/${basename_no_ext}.html" "${dest_html}"
        fi

        COUNT=$((COUNT + 1))
    fi
done

# Exporta também o README.org principal para web/docs/README.html
if [ -f "${ROOT_DIR}/README.org" ]; then
    echo "  📄 Exportando: README.org -> web/docs/README.html"
    emacs -Q --batch \
        --eval "${ELISP_EXPORT_CONFIG}" \
        --visit "${ROOT_DIR}/README.org" \
        --eval "(org-html-export-to-html)" \
        2>&1 | sed 's/^/     /'
    if [ -f "${ROOT_DIR}/README.html" ]; then
        mv "${ROOT_DIR}/README.html" "${DOCS_DEST_DIR}/README.html"
    fi
    COUNT=$((COUNT + 1))
fi

echo ""
echo "✅ Sucesso! ${COUNT} documentos exportados para ${DOCS_DEST_DIR}"
echo "========================================================================"
