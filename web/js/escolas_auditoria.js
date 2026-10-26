/**
 * ============================================================================
 * Auditoria do Georreferenciamento das Escolas (Censo Escolar 2024)
 * ============================================================================
 *
 * Mapa separado do mapa do usuário final (escolas_mapa.js): mostra de onde
 * veio a coordenada de cada escola (STATUS_GEOLOCALIZACAO do ETL).
 *
 *   inep_*         ponto do Catálogo de Escolas do INEP (cadastro de 2023,
 *                  via geobr/Ipea), conforme a distância até o ponto do CNEFE
 *   cep_numero     CNEFE, mesmo CEP + número        (escola sem ponto no INEP)
 *   nome_exato     CNEFE, mesmo nome + município    (idem)
 *   nome_ajustado  CNEFE, mesmo núcleo do nome + município (idem)
 *
 * Os dados vêm de web/data/auditoria/ (gerados por
 * scripts/commands/escolas_mapa__gerar_dados_auditoria.py). Os pontos são
 * desenhados em canvas, sem cluster, para que cada escola fique visível.
 */

const map = L.map("map", { center: [-14.235, -51.925], zoom: 4, preferCanvas: true });

const BASEMAPS = {
  osm: L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors | Dados: INEP, IBGE, Ipea',
    maxZoom: 19,
  }),
  "esri-satellite": L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { attribution: "Tiles &copy; Esri | Dados: INEP, IBGE, Ipea", maxZoom: 18 }
  ),
};
let basemapAtivo = BASEMAPS.osm.addTo(map);
document.getElementById("basemap-select").addEventListener("change", (e) => {
  map.removeLayer(basemapAtivo);
  basemapAtivo = BASEMAPS[e.target.value].addTo(map);
});

// ============================================================================
// Origens e cores
// ============================================================================
// Mesmas cores do mapa do usuário final (CONFIANCA_GEO em escolas_mapa.js)
const ORIGENS = {
  inep_confirmado: { nome: "INEP · confirmado pelo CNEFE (até 300 m)", cor: "#15803d" },
  inep_proximo: { nome: "INEP · CNEFE a 300 m-1 km", cor: "#65a30d" },
  inep_sem_cnefe: { nome: "INEP · sem ponto no CNEFE", cor: "#9333ea" },
  inep_divergente: { nome: "INEP · CNEFE a mais de 1 km", cor: "#ea580c" },
  cep_numero: { nome: "CNEFE · nível 1, CEP + número", cor: "#2563eb" },
  nome_exato: { nome: "CNEFE · nível 2a, nome exato + município", cor: "#0891b2" },
  nome_ajustado: { nome: "CNEFE · nível 2b, nome ajustado + município", cor: "#d4a106" },
};
const NOME_FONTE = { inep: "INEP", cnefe: "CNEFE" };
const STATUS_CNEFE = {
  cep_numero: "nível 1 (CEP + número)",
  nome_exato: "nível 2a (nome exato)",
  nome_ajustado: "nível 2b (nome ajustado)",
  sem_correspondencia: "sem correspondência",
};
const COR_FORA = "#dc2626";

const INDICE_URL = "data/auditoria/indice.json";
const MUNICIPIOS_URL = "data/BR_municipios_2024_minima.geojson";

const loading = document.getElementById("loading-indicator");
const pontosLayer = L.layerGroup().addTo(map);
const selecaoLayer = L.layerGroup().addTo(map);

let indice = null;
const escolasPorUf = {}; // uf -> [escola, ...]
const ufsAtivas = new Set();
const origensAtivas = new Set(Object.keys(ORIGENS));
let municipiosPorCodigo = null; // carregado só no primeiro clique

function escaparHtml(texto) {
  return String(texto ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatarKm(km) {
  return km == null ? "-" : km.toLocaleString("pt-BR", { maximumFractionDigits: 2 }) + " km";
}

function mostrarCarregando(texto) {
  loading.textContent = texto;
  loading.classList.toggle("hidden", !texto);
}

// ============================================================================
// Carregamento dos dados
// ============================================================================
async function carregarIndice() {
  indice = await (await fetch(INDICE_URL)).json();
  const container = document.getElementById("auditoria-ufs");
  container.innerHTML = "";
  for (const uf of Object.keys(indice.ufs)) {
    const info = indice.ufs[uf];
    const label = document.createElement("label");
    label.className = "checkbox-label";
    label.innerHTML = `<input type="checkbox" value="${uf}"> ${uf}
      <span class="escolas-uf-meta">(${info.total_escolas.toLocaleString("pt-BR")} escolas, ${(info.tamanho_bytes / 1e6).toFixed(1)} MB)</span>`;
    label.querySelector("input").addEventListener("change", (e) => alternarUf(uf, e.target.checked));
    container.appendChild(label);
  }
  renderOrigens();
}

async function carregarUf(uf) {
  if (escolasPorUf[uf]) return;
  mostrarCarregando(`Carregando ${uf}...`);
  try {
    const dados = await (await fetch(indice.ufs[uf].arquivo)).json();
    escolasPorUf[uf] = dados.escolas.map((linha) =>
      Object.fromEntries(dados.campos.map((campo, i) => [campo, linha[i]]))
    );
  } finally {
    mostrarCarregando("");
  }
}

async function alternarUf(uf, ligar) {
  if (ligar) {
    await carregarUf(uf);
    ufsAtivas.add(uf);
  } else {
    ufsAtivas.delete(uf);
  }
  renderTudo();
  const pontos = [...ufsAtivas].flatMap((u) => escolasPorUf[u].map((e) => [e.LATITUDE, e.LONGITUDE]));
  if (pontos.length) map.fitBounds(L.latLngBounds(pontos), { padding: [20, 20] });
}

async function carregarMunicipios() {
  if (municipiosPorCodigo) return municipiosPorCodigo;
  mostrarCarregando("Carregando malha municipal...");
  try {
    const geojson = await (await fetch(MUNICIPIOS_URL)).json();
    municipiosPorCodigo = Object.fromEntries(geojson.features.map((f) => [f.properties.codarea, f]));
  } finally {
    mostrarCarregando("");
  }
  return municipiosPorCodigo;
}

// ============================================================================
// Filtros
// ============================================================================
function lerFiltros() {
  return {
    soFora: document.getElementById("filtro-fora").checked,
    distanciaMin: document.getElementById("filtro-distancia").checked
      ? parseFloat(document.getElementById("filtro-distancia-km").value) || 0
      : null,
  };
}

function passaNoFiltro(escola, filtros) {
  if (!origensAtivas.has(escola.ORIGEM)) return false;
  if (filtros.soFora && !(escola.FORA_MUNICIPIO_KM > 0)) return false;
  if (filtros.distanciaMin != null && !(escola.DIST_INEP_CNEFE_KM > filtros.distanciaMin)) return false;
  return true;
}

function escolasFiltradas() {
  const filtros = lerFiltros();
  return [...ufsAtivas].flatMap((uf) => escolasPorUf[uf].filter((e) => passaNoFiltro(e, filtros)));
}

for (const id of ["filtro-fora", "filtro-distancia", "filtro-distancia-km"]) {
  document.getElementById(id).addEventListener(id.endsWith("km") ? "input" : "change", renderTudo);
}

// ============================================================================
// Desenho
// ============================================================================
function renderOrigens() {
  const container = document.getElementById("auditoria-origens");
  const contagem = Object.fromEntries(Object.keys(ORIGENS).map((o) => [o, 0]));
  let semPonto = 0;
  const ufs = ufsAtivas.size ? [...ufsAtivas] : Object.keys(indice.ufs);
  for (const uf of ufs) {
    for (const [origem, n] of Object.entries(indice.ufs[uf].por_origem)) {
      if (origem in contagem) contagem[origem] += n;
      else semPonto += n;
    }
  }
  container.innerHTML = "";
  for (const [origem, info] of Object.entries(ORIGENS)) {
    const label = document.createElement("label");
    label.className = "auditoria-origem";
    label.innerHTML = `<input type="checkbox" ${origensAtivas.has(origem) ? "checked" : ""}>
      <span class="legend-color" style="background:${info.cor}"></span> ${info.nome}
      <span class="contagem">${contagem[origem].toLocaleString("pt-BR")}</span>`;
    label.querySelector("input").addEventListener("change", (e) => {
      if (e.target.checked) origensAtivas.add(origem);
      else origensAtivas.delete(origem);
      renderTudo();
    });
    container.appendChild(label);
  }
  const sem = document.createElement("div");
  sem.className = "auditoria-origem";
  sem.title = "Sem correspondência no CNEFE e sem coordenada no cadastro do INEP: não aparecem no mapa";
  sem.innerHTML = `<span class="legend-color" style="background:transparent;border:1px dashed #94a3b8"></span>
    Sem ponto (fora do mapa) <span class="contagem">${semPonto.toLocaleString("pt-BR")}</span>`;
  container.appendChild(sem);
  const nota = document.createElement("p");
  nota.className = "instruction";
  nota.textContent = ufsAtivas.size ? "Contagens das UFs marcadas." : "Contagens de todas as UFs; marque uma UF para ver os pontos.";
  container.appendChild(nota);
}

function renderPontos(escolas) {
  pontosLayer.clearLayers();
  // Os pontos fora do município são desenhados por último, para ficarem por cima.
  const ordenadas = [...escolas].sort((a, b) => (a.FORA_MUNICIPIO_KM > 0) - (b.FORA_MUNICIPIO_KM > 0));
  for (const escola of ordenadas) {
    const fora = escola.FORA_MUNICIPIO_KM > 0;
    L.circleMarker([escola.LATITUDE, escola.LONGITUDE], {
      radius: fora ? 7 : 4,
      color: fora ? COR_FORA : "#ffffff",
      weight: fora ? 2.5 : 0.8,
      fillColor: ORIGENS[escola.ORIGEM].cor,
      fillOpacity: 0.9,
    })
      .on("click", () => selecionarEscola(escola))
      .addTo(pontosLayer);
  }
}

function renderResumo(escolas) {
  const fora = escolas.filter((e) => e.FORA_MUNICIPIO_KM > 0).length;
  const comAmbos = escolas.filter((e) => e.DIST_INEP_CNEFE_KM != null);
  const acima1 = comAmbos.filter((e) => e.DIST_INEP_CNEFE_KM > 1).length;
  document.getElementById("auditoria-resumo").innerHTML = `
    <div class="math-row"><span class="math-label">Escolas no mapa (filtro atual):</span>
      <span class="math-value">${escolas.length.toLocaleString("pt-BR")}</span></div>
    <div class="math-row"><span class="math-label">Fora do município declarado:</span>
      <span class="math-value">${fora.toLocaleString("pt-BR")}</span></div>
    <div class="math-row"><span class="math-label">Com ponto do INEP e do CNEFE:</span>
      <span class="math-value">${comAmbos.length.toLocaleString("pt-BR")}</span></div>
    <div class="math-row"><span class="math-label">… a mais de 1 km um do outro:</span>
      <span class="math-value">${acima1.toLocaleString("pt-BR")}</span></div>`;
}

const LIMITE_LISTA = 300;

function gravidade(escola) {
  return Math.max(escola.FORA_MUNICIPIO_KM || 0, escola.DIST_INEP_CNEFE_KM || 0);
}

function renderLista(escolas) {
  const lista = document.getElementById("auditoria-lista");
  const casos = escolas.filter((e) => gravidade(e) > 0).sort((a, b) => gravidade(b) - gravidade(a));
  lista.innerHTML = "";
  if (!casos.length) {
    lista.innerHTML = '<div class="empty-state">Nenhum caso com distância no filtro atual.</div>';
    return;
  }
  for (const escola of casos.slice(0, LIMITE_LISTA)) {
    const li = document.createElement("li");
    const partes = [];
    if (escola.FORA_MUNICIPIO_KM > 0) partes.push(`<span class="alerta">fora do município: ${formatarKm(escola.FORA_MUNICIPIO_KM)}</span>`);
    if (escola.DIST_INEP_CNEFE_KM != null) partes.push(`INEP × CNEFE: ${formatarKm(escola.DIST_INEP_CNEFE_KM)}`);
    li.innerHTML = `<span class="legend-color" style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${ORIGENS[escola.ORIGEM].cor}"></span>
      ${escaparHtml(escola.NO_ENTIDADE)}
      <span class="meta">${escaparHtml(escola.NO_MUNICIPIO)} · ${partes.join(" · ")}</span>`;
    li.addEventListener("click", () => selecionarEscola(escola, true));
    lista.appendChild(li);
  }
  if (casos.length > LIMITE_LISTA) {
    const mais = document.createElement("div");
    mais.className = "instruction";
    mais.textContent = `Mostrando ${LIMITE_LISTA} de ${casos.length.toLocaleString("pt-BR")} casos.`;
    lista.appendChild(mais);
  }
}

function renderTudo() {
  if (!indice) return;
  const escolas = escolasFiltradas();
  renderOrigens();
  renderPontos(escolas);
  renderResumo(escolas);
  renderLista(escolas);
}

// ============================================================================
// Seleção de uma escola: popup, município declarado e ponto do INEP
// ============================================================================
function linhaTabela(rotulo, valor) {
  return valor == null || valor === "" ? "" : `<tr><td class="label">${rotulo}</td><td>${valor}</td></tr>`;
}

function htmlEscola(escola) {
  const fora = escola.FORA_MUNICIPIO_KM > 0;
  return `<div class="escolas-popup">
    <h4>${escaparHtml(escola.NO_ENTIDADE)}</h4>
    <table>
      ${linhaTabela("Código INEP", escaparHtml(escola.CO_ENTIDADE))}
      ${linhaTabela("Origem", `<strong style="color:${ORIGENS[escola.ORIGEM].cor}">${ORIGENS[escola.ORIGEM].nome}</strong>`)}
      ${linhaTabela("Município declarado", escaparHtml(escola.NO_MUNICIPIO))}
      ${linhaTabela(
        "Município do ponto",
        fora
          ? `<span style="color:${COR_FORA};font-weight:600">${escaparHtml(escola.MUNICIPIO_DO_PONTO || "fora de todos (mar/rio?)")} · a ${formatarKm(escola.FORA_MUNICIPIO_KM)} do declarado</span>`
          : escaparHtml(escola.MUNICIPIO_DO_PONTO)
      )}
      ${linhaTabela("Endereço (INEP)", escaparHtml(escola.INEP_ENDERECO))}
      ${linhaTabela("Casamento com o CNEFE", escaparHtml(STATUS_CNEFE[escola.STATUS_CNEFE] || escola.STATUS_CNEFE))}
      ${linhaTabela("Estabelecimento (CNEFE)", escaparHtml(escola.CNEFE_DSC_ESTABELECIMENTO))}
      ${linhaTabela("Endereço (CNEFE)", escaparHtml(escola.CNEFE_ENDERECO))}
      ${linhaTabela("Nível coord. CNEFE", escola.CNEFE_NV_GEO_COORD)}
      ${linhaTabela("Similaridade do nome", escaparHtml(escola.SIMILARIDADE_NOME))}
      ${linhaTabela("Distância INEP × CNEFE", escola.DIST_INEP_CNEFE_KM != null ? formatarKm(escola.DIST_INEP_CNEFE_KM) : "")}
      ${linhaTabela("Motivo", escaparHtml(escola.MOTIVO))}
      ${linhaTabela("Alertas", escaparHtml(escola.ALERTAS))}
      ${linhaTabela("Coordenada", `${escola.LATITUDE}, ${escola.LONGITUDE}`)}
    </table>
  </div>`;
}

let selecaoAtual = 0;

async function selecionarEscola(escola, centralizar = false) {
  const minhaSelecao = ++selecaoAtual;
  const ponto = [escola.LATITUDE, escola.LONGITUDE];
  const limites = L.latLngBounds([ponto]);
  selecaoLayer.clearLayers();
  const popup = L.popup({ maxWidth: 380, autoPan: false }).setLatLng(ponto).setContent(htmlEscola(escola));
  abrirPopup(popup);

  if (escola.OUTRO_LATITUDE != null) {
    const outroPonto = [escola.OUTRO_LATITUDE, escola.OUTRO_LONGITUDE];
    const outro = NOME_FONTE[escola.OUTRO_FONTE];
    L.polyline([ponto, outroPonto], { color: "#475569", weight: 2, dashArray: "6 6" }).addTo(selecaoLayer);
    L.circleMarker(outroPonto, { radius: 6, color: "#0f172a", weight: 1.5, fillColor: "#ffffff", fillOpacity: 1 })
      .bindTooltip(`Ponto do ${outro}, não usado (${formatarKm(escola.DIST_INEP_CNEFE_KM)} do ponto usado)`)
      .addTo(selecaoLayer);
    limites.extend(outroPonto);
  }

  const municipios = await carregarMunicipios();
  if (minhaSelecao !== selecaoAtual) return; // outra escola foi clicada enquanto a malha carregava
  const municipio = municipios[escola.CO_MUNICIPIO];
  if (municipio) {
    const contorno = L.geoJSON(municipio, {
      style: { color: "#0f172a", weight: 2, dashArray: "4 4", fill: true, fillOpacity: 0.04 },
      interactive: false,
    }).addTo(selecaoLayer);
    if (escola.FORA_MUNICIPIO_KM > 0) limites.extend(contorno.getBounds());
  }
  if (centralizar || escola.FORA_MUNICIPIO_KM > 0 || escola.OUTRO_LATITUDE != null) {
    // Depois de enquadrar, reabre o popup deixando o Leaflet deslocar o mapa
    // para ele caber inteiro na tela.
    map.once("moveend", () => {
      if (minhaSelecao === selecaoAtual && popup.isOpen()) abrirPopup(popup.options.autoPan ? popup : L.popup({ maxWidth: 380 }).setLatLng(ponto).setContent(htmlEscola(escola)));
    });
    map.fitBounds(limites.pad(0.3), { maxZoom: 16 });
  }
}

// Fechar o popup limpa a seleção, a não ser quando é só a troca de um popup
// por outro (nova seleção ou reabertura).
let trocandoPopup = false;
function abrirPopup(popup) {
  trocandoPopup = true;
  popup.openOn(map);
  trocandoPopup = false;
}
map.on("popupclose", () => {
  if (!trocandoPopup) selecaoLayer.clearLayers();
});

carregarIndice();
