# Mapa do CNEAS – Cadastro Nacional de Entidades de Assistência Social

Branch: `feat/mapa-cneas`

## Goal

Plotar no mapa web todos os pontos do CNEAS (entidades de assistência social
da Rede SUAS e suas ofertas), lado a lado com as escolas já georreferenciadas,
para o mapeamento intersetorial educação x assistência social.

## Fonte

- Página: <https://dados.gov.br/dados/conjuntos-dados/cneas--cadastro-nacional-de-entidades-de-assistencia-social>
- Publicador: Ministério do Desenvolvimento e Assistência Social (MDS), via VIS DATA (SAGI).
- Licença: aberta / público. Atualização: "não verificável" no portal.
- 16 recursos: para cada ano **2023, 2024, 2025 e 2026**, duas tabelas
  (**Entidades** e **Ofertas**), cada uma em **CSV** e **JSON**. Catalogação de 2026: 02/02/2026.
- Acesso: a página do dados.gov.br só carrega o conteúdo pelo navegador, e a API
  `dados.gov.br/api/publico/...` responde **401** sem chave de acesso. **Os links
  diretos de download ainda não foram obtidos** (ver Tarefa 1).

### Campos (segundo o dicionário da página)

| Entidades (sede) | Ofertas (serviço ofertado) |
|---|---|
| `codigo_ibge`, `anomes` | `codigo_ibge`, `anomes` |
| `cneas_entidade_nome_municipio_s`, `cneas_entidade_sigla_uf_s` | `cneas_oferta_nome_municipio_s`, `cneas_oferta_sigla_uf_s` |
| `cneas_cod_entidade_s`, `cneas_entidade_numero_cnpj_s` | `cneas_oferta_numero_cnpj_s` |
| `cneas_entidade_razao_social_s`, `cneas_entidade_nome_fantasia_s` | `cneas_oferta_cod_servico_s`, `cneas_oferta_nome_servico_s` |
| — | `cneas_oferta_cod_nivel_protecao_s`, `cneas_oferta_desc_nivel_protecao_s` |
| `..._endereco_logradouro_s`, `_numero_s`, `_complemento_s`, `_bairro_s`, `_cep_s` | idem (`cneas_oferta_endereco_*`) |
| `cneas_entidade_situacao_cadastro_s`, `cneas_entidade_dt_extracao_s` | `cneas_oferta_dt_extracao_s` |

**O CNEAS não tem latitude/longitude**: só endereço, CEP e código IBGE do
município. Plotar os pontos exige **geocodificar**. Entidades e ofertas se
ligam pelo CNPJ, e a oferta tem endereço próprio, que pode ser diferente da sede.

## Scope

- Dentro: baixar o CNEAS mais recente (2026; os anos anteriores ficam para comparação
  posterior), geocodificar Entidades e Ofertas pelo endereço usando o CNEFE 2022
  (já baixado em `data/ibge_cnefe/`), gerar JSON por UF e uma camada no mapa web.
- Fora (por enquanto): séries históricas 2023–2025, cruzamento entidade x escola
  por proximidade (fica para uma feature seguinte).

## Task Breakdown

1. **Obter os links de download e escrever `scripts/commands/mds_cneas__baixar_dados.py`.**
   *Justificativa:* todo o pipeline do projeto parte de um download reprodutível,
   como `inep_censo_escolar__baixar_dados.py`. Como a API do dados.gov.br pede chave,
   é preciso o link direto do recurso (provavelmente no `aplicacoes.mds.gov.br/sagi`,
   ver "Acessar o recurso" na página).
2. **Explorar os CSVs com `scripts/utils/previsualizar_dados.py`.**
   *Justificativa:* confirmar encoding, separador, contagem de linhas, a qualidade
   do CEP/número e quantas ofertas têm endereço diferente da sede, antes de desenhar o casamento.
3. **Geocodificar contra o CNEFE: `scripts/commands/mds_cneas__georreferenciar.py`.**
   *Justificativa:* o CNEAS não traz coordenadas. O CNEFE 2022 tem latitude/longitude
   de cada endereço do país. Proposta em níveis, do mais preciso ao menos preciso, reaproveitando
   `scripts/utils/escolas_normalizacao.py` (`normalizar_cep`, `normalizar_numero`,
   `normalizar_logradouro`, `cep_generico`):
   - **G1:** CEP + logradouro + número batem → coordenada do endereço.
   - **G2:** CEP + logradouro, sem número → centro dos endereços da face/rua.
   - **G3:** CEP não genérico → centro dos endereços do CEP.
   - **G4:** só município → centro do município (ponto marcado como impreciso no mapa).
   Cada linha guarda o nível usado, para auditoria, como já se faz nas escolas.
4. **Gerar os dados do mapa: `scripts/commands/mds_cneas__gerar_dados_web.py`.**
   *Justificativa:* o mapa web carrega JSON compacto por UF (`web/data/...`),
   no mesmo padrão de `escolas_mapa__gerar_dados_web.py`, para caber no navegador.
5. **Camada CNEAS no mapa web (Leaflet).**
   *Justificativa:* é o objetivo da feature. Cores por nível de proteção
   (básica / especial média / especial alta), popup com nome, CNPJ, serviço e
   nível de geocodificação, e filtro liga/desliga ao lado das escolas.
6. **Documentar e registrar o resultado** (taxa por nível de geocodificação, por UF).
   *Justificativa:* a precisão da geocodificação define o quanto o mapa é confiável.

## What Was Done

- **2026-11-21:** branch `feat/mapa-cneas` criada a partir da `main` (`d72e9ef`).
- **2026-11-21:** página do conjunto lida pelo navegador: há 16 recursos
  (2023–2026, Entidades/Ofertas, CSV/JSON), o dicionário de campos foi registrado
  acima e ficou confirmada a ausência de coordenadas. A API do dados.gov.br respondeu 401
  sem chave, então os links diretos de download ainda estão pendentes (Tarefa 1).
