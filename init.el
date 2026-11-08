;;; init.el --- Configuração do Emacs para o georef-artifacts -*- lexical-binding: t -*-
;;
;; Projeto de estudo de georreferenciamento: documentação em Org,
;; scripts Python (geopandas) em scripts/commands/, mapas Leaflet em
;; web/ (HTML/CSS/JS + GeoJSON) e testes da API do IBGE em restclient.
;;
;; Uso (a partir da raiz do repositório):
;;   emacs -q -l init.el
;;
;; Ou defina um alias no rc do seu shell:
;;   alias emacs-georef='emacs -q -l ~/caminho/para/georef-artifacts/init.el'
;;
;; Ferramentas externas usadas (Fedora):
;;   - pyright (servidor LSP do Python): npm install -g pyright
;;   - hunspell + dicionário: sudo dnf install hunspell hunspell-pt-BR
;;   - .venv do projeto: ver docs/02-ambiente-python.org


;;; ---------------------------------------------------------------
;; 0a. Compilador nativo — silencia avisos falsos
;;     Na primeira compilação nativa dos pacotes, o compilador
;;     assíncrono processa cada arquivo isoladamente e não resolve
;;     referências entre arquivos.  Esses avisos não afetam o
;;     funcionamento; 'silent mantém a compilação e esconde o ruído.
;;; ---------------------------------------------------------------

(setq native-comp-async-report-warnings-errors 'silent)


;;; ---------------------------------------------------------------
;; 0b. Bootstrap de pacotes (straight.el + use-package)
;;     Todos os pacotes ficam num cache local .emacs-georef/ ao lado
;;     deste arquivo (ignorado no .gitignore), sem tocar no
;;     ~/.emacs.d do sistema.
;;; ---------------------------------------------------------------

(defconst georef/root-dir
  (file-name-directory (or load-file-name buffer-file-name))
  "Raiz do repositório — o diretório que contém este init.el.")

(defconst georef/cache-dir
  (expand-file-name ".emacs-georef/" georef/root-dir)
  "Cache local de pacotes — mantém o ~/.emacs.d do sistema limpo.")

;; Redireciona todos os arquivos efêmeros do Emacs para o cache local
(setq user-emacs-directory georef/cache-dir)
(setq package-user-dir (expand-file-name "elpa/" georef/cache-dir))

;; Bootstrap do straight.el
(defvar bootstrap-version)
(let ((bootstrap-file
       (expand-file-name "straight/repos/straight.el/bootstrap.el"
                         georef/cache-dir))
      (bootstrap-version 7))
  (unless (file-exists-p bootstrap-file)
    (with-current-buffer
        (url-retrieve-synchronously
         "https://raw.githubusercontent.com/radian-software/straight.el/develop/install.el"
         'silent 'inhibit-cookies)
      (goto-char (point-max))
      (eval-print-last-sexp)))
  (load bootstrap-file nil 'nomessage))

(straight-use-package 'use-package)
(setq straight-use-package-by-default t)
(setq use-package-always-ensure t)


;;; ---------------------------------------------------------------
;; 1. Ambiente virtual Python (.venv)
;;    Equivale a um "source .venv/bin/activate" para o Emacs inteiro:
;;    o shell interativo, o org-babel, os comandos M-x compile e os
;;    scripts do menu Georef usam todos o Python do projeto (com
;;    geopandas etc.), não o do sistema.
;;; ---------------------------------------------------------------

(defconst georef/venv-dir
  (expand-file-name ".venv/" georef/root-dir)
  "Ambiente virtual Python do projeto (ver docs/02-ambiente-python.org).")

(defconst georef/venv-python
  (expand-file-name "bin/python" georef/venv-dir)
  "Interpretador Python do .venv.")

(if (file-executable-p georef/venv-python)
    (let ((bin-dir (expand-file-name "bin/" georef/venv-dir)))
      (add-to-list 'exec-path bin-dir)
      (setenv "PATH" (concat bin-dir ":" (getenv "PATH")))
      (setenv "VIRTUAL_ENV" (directory-file-name georef/venv-dir)))
  (message "Georef: %s não encontrado — crie o .venv (docs/02-ambiente-python.org)"
           georef/venv-python))


;;; ---------------------------------------------------------------
;; 2. Interface e comportamento geral
;;; ---------------------------------------------------------------

(setq inhibit-startup-screen t
      initial-scratch-message nil
      ring-bell-function 'ignore)

(menu-bar-mode   1)    ; ligado para exibir o menu "Georef" (seção 13)
(tool-bar-mode   -1)
(scroll-bar-mode -1)
(column-number-mode 1)
(global-display-line-numbers-mode 1)
(show-paren-mode 1)
(global-auto-revert-mode 1)  ; os scripts regravam CSV/GeoJSON/HTML no disco

;; Os GeoJSON de web/data/ são uma única linha de vários MB.  O
;; so-long-mode detecta linhas gigantes e desliga o que travaria o
;; Emacs (realce, números de linha, LSP) ao abrir esses arquivos.
(global-so-long-mode 1)

;; Padrões sensatos
(setq-default indent-tabs-mode nil
              fill-column 80)
(setq sentence-end-double-space nil
      require-final-newline t)

;; Backups e auto-saves fora da árvore do projeto
(setq backup-directory-alist
      `(("." . ,(expand-file-name "backups/" georef/cache-dir)))
      auto-save-file-name-transforms
      `((".*" ,(expand-file-name "auto-save/" georef/cache-dir) t)))

;; Ao contrário de backup-directory-alist, o Emacs não cria o
;; diretório de auto-save sozinho.
(make-directory (expand-file-name "auto-save/" georef/cache-dir) t)


;;; ---------------------------------------------------------------
;; 3. Fontes — texto dos buffers e da interface
;;    Tenta Nerd Fonts instaladas à mão em ~/.local/share/fonts e
;;    cai para a DejaVu Sans Mono, que vem com o Fedora.  Os ícones
;;    do treemacs usam outra fonte (ver seção 12).
;;; ---------------------------------------------------------------

(defun georef/set-font ()
  "Aplica a primeira fonte disponível às faces default e fixed-pitch."
  (let ((font (seq-find (lambda (f) (member f (font-family-list)))
                         '("FiraCode Nerd Font Mono"
                           "JetBrainsMono Nerd Font Mono"
                           "Hack Nerd Font Mono"
                           "CaskaydiaCove Nerd Font Mono"
                           "Cascadia Mono NF"
                           "DejaVu Sans Mono"))))
    (when font
      (set-face-attribute 'default nil :family font :height 110)
      (set-face-attribute 'fixed-pitch nil :family font :height 110))))

;; Com "emacs -q -l init.el" este arquivo é carregado *depois* do
;; after-init-hook já ter rodado, então a fonte é aplicada na hora.
(if after-init-time
    (georef/set-font)
  (add-hook 'after-init-hook #'georef/set-font))


;;; ---------------------------------------------------------------
;; 4. Tema
;;; ---------------------------------------------------------------

(use-package modus-themes
  :config
  (modus-themes-load-theme 'modus-operandi))   ; claro; 'modus-vivendi para escuro


;;; ---------------------------------------------------------------
;; 5. Completion no minibuffer (Vertico + Orderless + Marginalia)
;;; ---------------------------------------------------------------

(use-package vertico
  :init (vertico-mode 1))

(use-package orderless
  :custom
  (completion-styles '(orderless basic))
  (completion-category-overrides '((file (styles basic partial-completion)))))

(use-package marginalia
  :init (marginalia-mode 1))


;;; ---------------------------------------------------------------
;; 5b. Popup de completion no buffer (Corfu + Cape)
;;     Corfu só desenha o popup; as sugestões vêm de
;;     `completion-at-point-functions' — do eglot (pyright) no
;;     Python e, via Cape, de palavras dos buffers abertos e de
;;     caminhos de arquivo no Org/Markdown.
;;; ---------------------------------------------------------------

(use-package corfu
  :init
  (global-corfu-mode 1)
  :custom
  (corfu-cycle t)
  (corfu-quit-no-match t)
  (corfu-on-exact-match nil)
  ;; O primeiro candidato já vem selecionado: aceitar é um TAB.  Isso
  ;; só é seguro porque o RET foi desligado no corfu-map abaixo —
  ;; senão todo Enter em texto corrido completaria uma palavra.
  (corfu-preselect 'first)
  ;; Não escreve o candidato no buffer antes do TAB (evita o texto
  ;; "piscando" sob o cursor e o flyspell checando meias-palavras).
  (corfu-preview-current nil)
  :bind
  (:map corfu-map
        ("RET"    . nil)
        ([return] . nil)
        ("TAB"    . corfu-insert)
        ([tab]    . corfu-insert)
        ("C-n"    . corfu-next)
        ("C-p"    . corfu-previous)
        ("C-g"    . corfu-quit))
  :config
  ;; Desde o Corfu 2.8 o auto-completion fica em corfu-auto.el, que
  ;; precisa ser carregado antes de se ajustar as variáveis abaixo.
  (require 'corfu-auto)
  (setq corfu-auto t
        corfu-auto-delay 0.2
        corfu-auto-prefix 3
        ;; "." abre o popup na hora: atributos e métodos no Python
        ;; (gdf.to_crs, pd.read_csv...).
        corfu-auto-trigger ".")

  ;; Painel lateral com a documentação do candidato (docstrings vindas
  ;; do pyright no Python).
  (require 'corfu-popupinfo)
  (corfu-popupinfo-mode 1)
  (setq corfu-popupinfo-delay '(0.5 . 0.3)))

;; NOTA: o popup do Corfu é um child frame, que só existe no modo
;; gráfico até o Emacs 30; em "emacs -nw" ele não aparece.

(use-package cape
  ;; Carregado de imediato: as opções abaixo são defcustoms que só
  ;; passam a existir quando cape.el é carregado.
  :demand t
  :init
  (defun georef/prose-capf-setup ()
    "Acrescenta palavras dos buffers abertos e caminhos de arquivo.
Com profundidade alta, para ficarem *depois* das fontes do próprio modo."
    (add-hook 'completion-at-point-functions #'cape-file    90 t)
    (add-hook 'completion-at-point-functions #'cape-dabbrev 95 t))
  (add-hook 'org-mode-hook      #'georef/prose-capf-setup)
  (add-hook 'markdown-mode-hook #'georef/prose-capf-setup)
  :custom
  ;; Termos longos (Censo Escolar, CNEFE, malha municipal...) se
  ;; repetem entre os .org, então as palavras vêm de todos os buffers
  ;; do mesmo modo, não só do atual.
  (cape-dabbrev-buffer-function #'cape-same-mode-buffers)
  ;; cape-file só se oferece quando há um "/" com diretório existente
  ;; antes do cursor (ex.: data/ibge_malha_municipal/...).
  (cape-file-directory-must-exist t))


;;; ---------------------------------------------------------------
;; 6. Python — python-mode + eglot (pyright)
;;    O pyright resolve os imports (geopandas, pandas, shapely...)
;;    pelo Python do .venv, informado em `eglot-workspace-configuration'.
;;; ---------------------------------------------------------------

(use-package python
  :straight nil
  :custom
  (python-shell-interpreter georef/venv-python)
  (python-shell-virtualenv-root georef/venv-dir)
  (python-indent-guess-indent-offset-verbose nil))

(use-package eglot
  :straight nil
  :hook (python-mode . eglot-ensure)
  :custom
  (eglot-autoshutdown t)          ; encerra o servidor ao fechar o último buffer
  (eglot-events-buffer-config '(:size 0 :format full))  ; sem log, mais leve
  :config
  ;; O eglot tenta o pylsp antes do pyright; aqui fixamos o pyright.
  (add-to-list 'eglot-server-programs
               '((python-mode python-ts-mode) "pyright-langserver" "--stdio"))
  (setq-default eglot-workspace-configuration
                `(:python (:pythonPath ,georef/venv-python
                           :analysis (:typeCheckingMode "basic"))))
  :bind
  (:map eglot-mode-map
        ("C-c l r" . eglot-rename)
        ("C-c l a" . eglot-code-actions)
        ("C-c l f" . eglot-format-buffer)
        ("C-c l d" . eldoc-doc-buffer)))


;;; ---------------------------------------------------------------
;; 7. Org-mode — documentação (README, docs/, analises/)
;;    Os blocos #+begin_src python/sh rodam com C-c C-c usando o
;;    Python do .venv.  A publicação em web/docs/ continua sendo feita
;;    pelo script exportar_docs_org_para_html.sh (menu Georef).
;;; ---------------------------------------------------------------

(use-package org
  :straight nil
  :mode ("\\.org\\'" . org-mode)
  :hook (org-mode . visual-line-mode)
  :custom
  (org-startup-folded 'content)
  (org-hide-leading-stars t)
  (org-src-fontify-natively t)
  (org-src-tab-acts-natively t)
  (org-src-preserve-indentation t)   ; Python é sensível à indentação
  (org-edit-src-content-indentation 0)
  (org-babel-python-command georef/venv-python)
  (org-export-with-sub-superscripts '{})  ; nomes_com_underscore não viram subscrito
  (org-html-validation-link nil)
  :config
  (org-babel-do-load-languages
   'org-babel-load-languages
   '((emacs-lisp . t)
     (python     . t)
     (shell      . t))))

;; Realce de sintaxe dos blocos de código no export HTML (C-c C-e h h)
(use-package htmlize)


;;; ---------------------------------------------------------------
;; 8. Web — mapas Leaflet em web/ (HTML, CSS, JS, GeoJSON)
;;    HTML, CSS e JS usam os modos nativos do Emacs (mhtml-mode,
;;    css-mode, js-mode).  GeoJSON é JSON; os arquivos grandes caem
;;    no so-long-mode (seção 2).
;;; ---------------------------------------------------------------

(use-package js
  :straight nil
  :mode ("\\.geojson\\'" . js-json-mode)
  :custom
  (js-indent-level 2))

(use-package css-mode
  :straight nil
  :custom
  (css-indent-offset 2))


;;; ---------------------------------------------------------------
;; 9. Outros formatos — Markdown, YAML, CSV
;;; ---------------------------------------------------------------

;; Análises em .md na raiz do repositório
(use-package markdown-mode
  :mode ("\\.md\\'" . gfm-mode)
  :hook (markdown-mode . visual-line-mode))

;; .github/workflows/pages.yml
(use-package yaml-mode
  :mode ("\\.ya?ml\\'" . yaml-mode))

;; CSVs das análises e dos dados do INEP/CNEFE.
;; C-c C-a alinha as colunas, C-c C-s ordena, C-c C-t transpõe.
(use-package csv-mode
  :mode ("\\.csv\\'" . csv-mode)
  :hook (csv-mode . csv-guess-set-separator))  ; detecta "," ou ";" (padrão do INEP)


;;; ---------------------------------------------------------------
;; 10. Restclient — testes da API de Malhas do IBGE
;;     Abre scripts/restclient-ibge-malhas-api.http em restclient-mode;
;;     C-c C-c envia a requisição sob o cursor.
;;; ---------------------------------------------------------------

(use-package restclient
  :mode ("\\.http\\'" . restclient-mode))


;;; ---------------------------------------------------------------
;; 11. Flyspell — correção ortográfica (português do Brasil)
;;     Texto corrido (Org, Markdown) é checado por inteiro; no Python
;;     e no shell, só comentários e strings.  JSON, CSV e GeoJSON
;;     ficam de fora de propósito.
;;     Instalar: sudo dnf install hunspell hunspell-pt-BR
;;; ---------------------------------------------------------------

(use-package flyspell
  :straight nil
  :hook
  (org-mode      . flyspell-mode)
  (markdown-mode . flyspell-mode)
  (python-mode   . flyspell-prog-mode)
  (sh-mode       . flyspell-prog-mode)
  :custom
  (ispell-program-name "hunspell")
  (ispell-dictionary "pt_BR")   ; troque com M-x ispell-change-dictionary
  :config
  ;; O flyspell só marca uma palavra quando o cursor passa por ela.
  ;; Força a checagem do buffer inteiro ao ligar o modo de texto, para
  ;; os erros já aparecerem ao rolar a página.
  (add-hook 'flyspell-mode-hook
            (lambda ()
              (when (and flyspell-mode (not (derived-mode-p 'prog-mode)))
                (flyspell-buffer)))))


;;; ---------------------------------------------------------------
;; 12. Navegação — project.el, Magit e Treemacs
;;; ---------------------------------------------------------------

(use-package project
  :straight nil
  :config
  ;; Registra a raiz do repositório diretamente como projeto Git.
  (when (file-directory-p (expand-file-name ".git" georef/root-dir))
    (project-remember-project `(vc Git ,georef/root-dir))))

(use-package magit
  :bind
  ("C-x g" . magit-status))

(use-package treemacs
  :bind
  (("<f8>"      . treemacs-select-window)
   ("M-0"       . treemacs-select-window)
   ("C-x t t"   . treemacs)
   ("C-x t d"   . treemacs-select-directory)
   ("C-x t B"   . treemacs-bookmark)
   ("C-x t C-t" . treemacs-find-file)
   ("C-x t M-t" . treemacs-find-tag))
  :custom
  (treemacs-width 35)
  (treemacs-is-never-other-window t)
  (treemacs-sorting 'alphabetic-case-insensitive-asc)
  :config
  (treemacs-follow-mode t)
  (treemacs-filewatch-mode t)
  (treemacs-fringe-indicator-mode 'always)
  (treemacs-git-mode 'deferred)
  ;; .venv/, venv/ e __pycache__ só poluem a árvore
  (add-to-list 'treemacs-ignored-file-predicates
               (lambda (file _path)
                 (member file '(".venv" "venv" "__pycache__" ".emacs-georef")))))

(use-package treemacs-nerd-icons
  :after treemacs
  :config
  ;; Os ícones usam `nerd-icons-font-family' ("Symbols Nerd Font
  ;; Mono"), que não está nos repositórios do Fedora.  Instale uma vez
  ;; com M-x nerd-icons-install-fonts; até lá, fica o tema padrão do
  ;; treemacs em vez de quadradinhos vazios.
  (cond
   ((not (display-graphic-p))
    (treemacs-load-theme "nerd-icons"))
   ((find-font (font-spec :family nerd-icons-font-family))
    (treemacs-load-theme "nerd-icons"))
   (t
    (message "Treemacs: fonte %S não instalada — rode M-x nerd-icons-install-fonts"
             nerd-icons-font-family))))

;; Abre o treemacs na inicialização, já apontado para a raiz do
;; repositório (sem perguntar o caminho, como faria o `treemacs' puro).
(add-hook 'emacs-startup-hook
          (lambda ()
            (let ((default-directory georef/root-dir))
              (treemacs-add-and-display-current-project-exclusively))))


;;; ---------------------------------------------------------------
;; 13. Menu "Georef" — tarefas do projeto
;;     - exportar a documentação Org para web/docs/
;;     - rodar um script de scripts/commands/ com o Python do .venv
;;     - servir web/ em http://localhost:8000 (o Leaflet carrega os
;;       GeoJSON via fetch, que não funciona abrindo o HTML como file://)
;;; ---------------------------------------------------------------

(defconst georef/web-port 8000
  "Porta do servidor local de web/ (a mesma de docs/04-leaflet-explicado.org).")

(defun georef/exportar-docs ()
  "Exporta docs/*.org para web/docs/ via exportar_docs_org_para_html.sh."
  (interactive)
  (let ((default-directory georef/root-dir))
    (compile "./scripts/commands/exportar_docs_org_para_html.sh")))

(defun georef/rodar-script (script)
  "Roda SCRIPT de scripts/commands/ com o Python do .venv, num buffer *compilation*."
  (interactive
   (list (completing-read
          "Script: "
          (directory-files (expand-file-name "scripts/commands/" georef/root-dir)
                           nil "\\.py\\'")
          nil t)))
  (let ((default-directory georef/root-dir))
    (compile (format "%s scripts/commands/%s"
                     (shell-quote-argument georef/venv-python)
                     (shell-quote-argument script)))))

(defun georef/servidor-web ()
  "Liga ou desliga o servidor HTTP local de web/ e abre o navegador."
  (interactive)
  (let ((proc (get-process "georef-servidor-web")))
    (if (process-live-p proc)
        (progn (delete-process proc)
               (message "Georef: servidor web parado."))
      (let ((default-directory georef/root-dir))
        (start-process "georef-servidor-web" "*georef-servidor-web*"
                       "python3" "-m" "http.server"
                       (number-to-string georef/web-port) "--directory" "web"))
      (message "Georef: servindo web/ em http://localhost:%d (rode de novo para parar)"
               georef/web-port)
      (run-at-time 1 nil #'browse-url
                   (format "http://localhost:%d" georef/web-port)))))

(keymap-global-set "C-c g e" #'georef/exportar-docs)
(keymap-global-set "C-c g r" #'georef/rodar-script)
(keymap-global-set "C-c g s" #'georef/servidor-web)

(easy-menu-define georef/menu global-map "Tarefas do projeto georef-artifacts."
  '("Georef"
    ["Exportar docs Org → web/docs/" georef/exportar-docs t]
    ["Rodar script de scripts/commands/..." georef/rodar-script t]
    "--"
    ["Servidor web local (liga/desliga)" georef/servidor-web t]))


;;; ---------------------------------------------------------------
;; 14. Resumo dos atalhos
;;
;;  Projeto (menu Georef):
;;    C-c g e       — exportar docs/*.org para web/docs/
;;    C-c g r       — rodar um script de scripts/commands/ com o .venv
;;    C-c g s       — liga/desliga http://localhost:8000 servindo web/
;;
;;  Python (eglot + pyright):
;;    M-.  / M-,    — ir para a definição / voltar
;;    C-c l r       — renomear símbolo
;;    C-c l a       — code actions (ex.: adicionar import)
;;    C-c l f       — formatar o buffer
;;    C-c l d       — documentação do símbolo sob o cursor
;;    C-c C-p       — abrir o shell Python (do .venv)
;;    C-c C-c       — enviar o buffer para o shell
;;    M-g n / M-g p — próximo / anterior erro (flymake)
;;
;;  Org:
;;    C-c C-c       — rodar o bloco #+begin_src sob o cursor
;;    C-c '         — editar o bloco de código em buffer próprio
;;    C-c C-e h o   — exportar para HTML e abrir no navegador
;;
;;  Restclient (arquivos .http):
;;    C-c C-c       — enviar a requisição sob o cursor
;;    C-c C-n / C-p — próxima / anterior requisição
;;
;;  CSV:
;;    C-c C-a       — alinhar colunas    C-c C-u — desalinhar
;;    C-c C-s       — ordenar por coluna
;;
;;  Popup de completion (Corfu — aparece sozinho ao digitar):
;;    TAB           — aceitar o candidato destacado
;;    C-n / C-p     — próximo / anterior candidato
;;    RET           — de propósito NÃO completa; insere nova linha
;;    C-g           — fechar o popup
;;    C-M-i         — forçar o popup
;;    M-t           — liga/desliga o painel de documentação
;;
;;  Treemacs (abre sozinho na inicialização):
;;    <f8> / M-0    — ir para a janela do treemacs
;;    C-x t t       — abrir/fechar o treemacs
;;    C-x t C-t     — localizar o arquivo atual no treemacs
;;
;;  Magit:
;;    C-x g         — magit-status
;;; ---------------------------------------------------------------

(provide 'init)
;;; init.el ends here
