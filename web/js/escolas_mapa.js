/**
 * ============================================================================
 * Mapa de Escolas Georreferenciadas (Censo Escolar 2024 + CNEFE 2022)
 * ============================================================================
 *
 * Cópia de app.js (Explorador de Malhas do IBGE), mantida separada para que o
 * explorador original continue intocado. Acrescenta o PASSO 11 (camada de
 * escolas com clusters, filtros e popups) ao final do arquivo.
 *
 * Conceitos herdados do explorador de malhas:
 *   1. Inicialização do Mapa (L.map)
 *   2. Gerenciamento Dinâmico de TileLayers (CartoDB, OSM, Esri, OpenTopo)
 *   3. Grade de Depuração de Tiles (L.GridLayer com exibição de Z, X, Y)
 *   4. Cálculo Matemático da Pirâmide de Tiles em Tempo Real (2^Z × 2^Z)
 *   5. Inspeção de Requisições GeoJSON do IBGE (Origem, Payload, Tempo de Carga)
 *   6. Auto-Seleção de Recorte Territorial por Zoom (Nível de Detalhe / LOD)
 *   7. Estilização Vetorial e Temática (cores por região)
 *   8. Eventos e Interatividade (hover, click, tooltips, painel)
 */

// ============================================================================
// PASSO 1: Inicializar o Mapa Leaflet
// ============================================================================
const map = L.map("map", {
  center: [-14.235, -51.925],
  zoom: 4,
  minZoom: 0,
  maxZoom: 18,
  zoomSnap: 1, // Trava o zoom em inteiros para facilitar a visualização dos tiles
  zoomDelta: 1,
});

// ============================================================================
// PASSO 2: Metadados dos Recortes GeoJSON do IBGE
// ============================================================================
const GEOJSON_METADATA = {
  pais: {
    fileName: "BR_pais_2024_minima.geojson",
    filePath: "data/BR_pais_2024_minima.geojson",
    ibgeApiUrl:
      "https://servicodados.ibge.gov.br/api/v4/malhas/paises/BR?qualidade=minima&formato=application/vnd.geo+json",
    description: "Contorno Nacional do Brasil",
    featuresExpected: 1,
    sizeEstimate: "15 KB",
    recommendedZoom: "Z = 0 a 3",
  },
  regioes: {
    fileName: "BR_regioes_2024_minima.geojson",
    filePath: "data/BR_regioes_2024_minima.geojson",
    ibgeApiUrl:
      "https://servicodados.ibge.gov.br/api/v4/malhas/paises/BR?qualidade=minima&formato=application/vnd.geo+json&intrarregiao=regiao",
    description: "5 Grandes Regiões (N, NE, CO, SE, S)",
    featuresExpected: 5,
    sizeEstimate: "33 KB",
    recommendedZoom: "Z = 4",
  },
  uf: {
    fileName: "BR_uf_2024_minima.geojson",
    filePath: "data/BR_uf_2024_minima.geojson",
    ibgeApiUrl:
      "https://servicodados.ibge.gov.br/api/v4/malhas/paises/BR?qualidade=minima&formato=application/vnd.geo+json&intrarregiao=UF",
    description: "27 Unidades da Federação (Estados e DF)",
    featuresExpected: 27,
    sizeEstimate: "117 KB",
    recommendedZoom: "Z = 5 a 7",
  },
  municipios: {
    fileName: "BR_municipios_2024_minima.geojson",
    filePath: "data/BR_municipios_2024_minima.geojson",
    ibgeApiUrl:
      "https://servicodados.ibge.gov.br/api/v4/malhas/paises/BR?qualidade=minima&formato=application/vnd.geo+json&intrarregiao=municipio",
    description: "5.571 Municípios Brasileiros",
    featuresExpected: 5571,
    sizeEstimate: "5.3 MB",
    recommendedZoom: "Z = 8 a 18",
  },
};

// ============================================================================
// PASSO 3: Provedores de TileLayers (Mapas Base Dinâmicos)
// ============================================================================
const BASEMAP_PROVIDERS = {
  "carto-light": {
    name: "CartoDB Positron (Claro)",
    url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    options: {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a> | Dados: <a href="https://www.ibge.gov.br">IBGE 2024</a>',
      subdomains: "abcd",
      maxZoom: 19,
    },
    description:
      "<strong>CartoDB Positron:</strong> Fundo claro e minimalista, ideal para destacar mapas temáticos e polígonos sem poluição visual.",
  },
  "carto-dark": {
    name: "CartoDB Dark Matter (Escuro)",
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    options: {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a> | Dados: <a href="https://www.ibge.gov.br">IBGE 2024</a>',
      subdomains: "abcd",
      maxZoom: 19,
    },
    description:
      "<strong>CartoDB Dark Matter:</strong> Modo escuro de alto contraste, ideal para visualizações noturnas ou polígonos fluorescentes.",
  },
  "osm": {
    name: "OpenStreetMap (Padrão)",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    options: {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors | Dados: <a href="https://www.ibge.gov.br">IBGE 2024</a>',
      maxZoom: 19,
    },
    description:
      "<strong>OpenStreetMap Padrão:</strong> Mapa rico em detalhes urbanos, nomes de vias, bairros, rios e relevo clássico.",
  },
  "esri-satellite": {
    name: "Esri World Imagery (Satélite)",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    options: {
      attribution:
        'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community | Dados: <a href="https://www.ibge.gov.br">IBGE 2024</a>',
      maxZoom: 18,
    },
    description:
      "<strong>Esri Satélite:</strong> Fotografias reais de satélite em alta resolução para inspecionar cobertura vegetal, rios e relevo real.",
  },
  "opentopo": {
    name: "OpenTopoMap (Topográfico)",
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    options: {
      attribution:
        'Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC-BY-SA</a>) | Dados: <a href="https://www.ibge.gov.br">IBGE 2024</a>',
      maxZoom: 17,
    },
    description:
      "<strong>OpenTopoMap:</strong> Mapa topográfico com relevo sombreado e curvas de nível de elevação.",
  },
};

let currentBasemapLayer = null;

function setBasemap(providerKey) {
  const provider = BASEMAP_PROVIDERS[providerKey];
  if (!provider) return;

  if (currentBasemapLayer) {
    map.removeLayer(currentBasemapLayer);
  }

  currentBasemapLayer = L.tileLayer(provider.url, provider.options);
  currentBasemapLayer.addTo(map);
  currentBasemapLayer.bringToBack();

  const descEl = document.getElementById("basemap-desc");
  const urlEl = document.getElementById("basemap-url");
  if (descEl) descEl.innerHTML = provider.description;
  if (urlEl) urlEl.textContent = provider.url;

  updateTilePyramidStats();
}

// ============================================================================
// PASSO 4: Grade de Depuração de Tiles (Exposição Visual Z, X, Y)
// ============================================================================
const TileDebugGrid = L.GridLayer.extend({
  createTile: function (coords) {
    const tile = document.createElement("div");
    tile.className = "debug-tile-grid";
    tile.innerHTML = `
      <div class="tile-coords-tag">
        <span class="z-tag">Z: ${coords.z}</span><br>
        <span class="xy-tag">X: ${coords.x}</span><br>
        <span class="xy-tag">Y: ${coords.y}</span>
      </div>
    `;
    return tile;
  },
});

const debugGridLayer = new TileDebugGrid({
  zIndex: 500,
});
// Nesta página a grade começa desligada (os rótulos Z/X/Y poluem os pontos das escolas)
if (document.getElementById("toggle-grid")?.checked) {
  debugGridLayer.addTo(map);
}

// ============================================================================
// PASSO 5: Matemática da Pirâmide de Tiles (Slippy Map)
// ============================================================================
function latLngToTileCoords(lat, lng, zoom) {
  const n = Math.pow(2, zoom);
  const x = Math.floor(((lng + 180) / 360) * n);
  const latRad = (lat * Math.PI) / 180;
  const y = Math.floor(
    ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n
  );
  return {
    x: Math.max(0, Math.min(n - 1, x)),
    y: Math.max(0, Math.min(n - 1, y)),
  };
}

/**
 * Calcula a faixa de tiles (X_min..X_max, Y_min..Y_max) visíveis no viewport da tela.
 */
function getVisibleTilesRange(zoom) {
  const bounds = map.getBounds();
  const nw = bounds.getNorthWest();
  const se = bounds.getSouthEast();

  const nwTile = latLngToTileCoords(nw.lat, nw.lng, zoom);
  const seTile = latLngToTileCoords(se.lat, se.lng, zoom);

  const minX = Math.min(nwTile.x, seTile.x);
  const maxX = Math.max(nwTile.x, seTile.x);
  const minY = Math.min(nwTile.y, seTile.y);
  const maxY = Math.max(nwTile.y, seTile.y);

  const countX = maxX - minX + 1;
  const countY = maxY - minY + 1;
  const total = countX * countY;

  return { minX, maxX, minY, maxY, countX, countY, total };
}

/**
 * Atualiza o painel lateral com as métricas em tempo real.
 */
function updateTilePyramidStats() {
  const zoom = Math.round(map.getZoom());
  const center = map.getCenter();
  const tileCoords = latLngToTileCoords(center.lat, center.lng, zoom);
  const dimension = Math.pow(2, zoom);
  const totalTiles = Math.pow(4, zoom);
  const visible = getVisibleTilesRange(zoom);

  // Atualiza os elementos da interface
  const zoomDisplay = document.getElementById("zoom-display-value");
  const zoomSlider = document.getElementById("zoom-slider");
  const mathGridDim = document.getElementById("math-grid-dim");
  const mathTotalTiles = document.getElementById("math-total-tiles");
  const mathCenterTile = document.getElementById("math-center-tile");
  const visibleTilesEl = document.getElementById("info-visible-tiles");

  if (zoomDisplay) zoomDisplay.textContent = zoom;
  if (zoomSlider) zoomSlider.value = zoom;
  if (mathGridDim) mathGridDim.textContent = `${dimension.toLocaleString("pt-BR")} × ${dimension.toLocaleString("pt-BR")}`;
  if (mathTotalTiles) mathTotalTiles.textContent = `${totalTiles.toLocaleString("pt-BR")} tiles`;
  if (mathCenterTile) mathCenterTile.textContent = `Z: ${zoom} | X: ${tileCoords.x} | Y: ${tileCoords.y}`;
  if (visibleTilesEl) {
    visibleTilesEl.textContent = `X: ${visible.minX}..${visible.maxX}, Y: ${visible.minY}..${visible.maxY} (${visible.total} tiles)`;
  }

  // Atualiza estado ativo dos botões de preset
  document.querySelectorAll(".btn-preset").forEach((btn) => {
    btn.classList.toggle("active", Number(btn.dataset.zoom) === zoom);
  });

  // Atualiza a URL real de exemplo para o tile central
  const basemapSelect = document.getElementById("basemap-select");
  const currentProviderKey = basemapSelect ? basemapSelect.value : "carto-light";
  const provider = BASEMAP_PROVIDERS[currentProviderKey];
  if (provider) {
    const sampleUrl = provider.url
      .replace("{s}", "a")
      .replace("{z}", zoom)
      .replace("{x}", tileCoords.x)
      .replace("{y}", tileCoords.y)
      .replace("{r}", "");
    const sampleUrlEl = document.getElementById("basemap-sample-url");
    if (sampleUrlEl) sampleUrlEl.textContent = sampleUrl;
  }
}

// ============================================================================
// PASSO 6: Paleta de Cores e Estilização Vetorial (GeoJSON)
// ============================================================================
const REGION_COLORS = {
  "1": "#2b83ba", // Norte
  "Norte": "#2b83ba",
  "N": "#2b83ba",

  "2": "#abdda4", // Nordeste
  "Nordeste": "#abdda4",
  "NE": "#abdda4",

  "5": "#ffffbf", // Centro-Oeste
  "Centro-Oeste": "#ffffbf",
  "CO": "#ffffbf",

  "3": "#fdae61", // Sudeste
  "Sudeste": "#fdae61",
  "SE": "#fdae61",

  "4": "#d7191c", // Sul
  "Sul": "#d7191c",
  "S": "#d7191c",
};

// Cor neutra única para o Contorno do País (não pertence a nenhuma região)
const PAIS_COLOR = "#64748b";

// Paleta categórica (sem relação com as cores de região) usada para diferenciar
// Municípios adjacentes e destacá-los sobre a camada de UF combinada por baixo
const MUNICIPIO_PALETTE = [
  "#f97316", "#a855f7", "#14b8a6", "#eab308",
  "#ec4899", "#22c55e", "#0ea5e9", "#f43f5e",
  "#84cc16", "#8b5cf6", "#06b6d4", "#d946ef",
];

// Variações de luminosidade aplicadas sobre a cor-base da região para diferenciar as UFs
// mantendo a identidade visual da região (tons do mesmo matiz)
const UF_LIGHTNESS_STEPS = [0, -16, 14, -28, 26, -8, 8, 20, -20];

/** Hash determinístico (djb2) — mesma feição sempre recebe a mesma cor/tom entre recargas. */
function hashString(str) {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = (hash * 33) ^ str.charCodeAt(i);
  }
  return Math.abs(hash);
}

function hexToHsl(hex) {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0;
  let s = 0;

  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      default: h = (r - g) / d + 4;
    }
    h /= 6;
  }

  return { h: h * 360, s: s * 100, l: l * 100 };
}

function hslToHex(h, s, l) {
  s /= 100;
  l /= 100;
  const k = (n) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  const toHex = (x) => Math.round(255 * x).toString(16).padStart(2, "0");
  return `#${toHex(f(0))}${toHex(f(8))}${toHex(f(4))}`;
}

function getRegionBaseColor(properties) {
  const regId = properties.cd_regiao || properties.sigla_regiao || properties.sigla || properties.nome;
  return REGION_COLORS[regId] || "#60a5fa";
}

/** UF: tom derivado da cor da própria região, variando a luminosidade por estado. */
function getUfColor(properties) {
  const baseColor = getRegionBaseColor(properties);
  const hsl = hexToHsl(baseColor);
  const ufKey = properties.sigla || properties.codarea || properties.nome || "";
  const stepIndex = hashString(String(ufKey)) % UF_LIGHTNESS_STEPS.length;
  const lightness = Math.min(80, Math.max(22, hsl.l + UF_LIGHTNESS_STEPS[stepIndex]));
  return hslToHex(hsl.h, hsl.s, lightness);
}

/** Municípios: paleta categórica independente da região, para contrastar com a UF por baixo. */
function getMunicipioColor(properties) {
  const key = properties.codarea || properties.nome || "";
  const index = hashString(String(key)) % MUNICIPIO_PALETTE.length;
  return MUNICIPIO_PALETTE[index];
}

/**
 * Escolhe a cor de preenchimento de acordo com a malha (layerKey), para que
 * camadas combinadas (ex.: UF + Municípios) permaneçam visualmente distinguíveis:
 *  - País: cor única neutra (sem noção de região)
 *  - Regiões: cor fixa por região
 *  - UF: tom da cor da região, variando por estado
 *  - Municípios: paleta categórica própria, sem relação com a região
 */
function getFeatureColor(properties, layerKey) {
  if (!properties) return "#3b82f6";

  switch (layerKey) {
    case "pais":
      return PAIS_COLOR;
    case "uf":
      return getUfColor(properties);
    case "municipios":
      return getMunicipioColor(properties);
    case "regioes":
    default:
      return getRegionBaseColor(properties);
  }
}

// Cor e espessura do contorno da UF — mais grossa e escura para que o "perfil" dos
// estados continue perceptível mesmo quando os Municípios são combinados por cima.
const UF_BORDER_COLOR = "#1e293b";
const UF_BORDER_WEIGHT = 2.2;

function getStyle(feature, layerKey) {
  const isUf = layerKey === "uf";
  return {
    fillColor: getFeatureColor(feature.properties, layerKey),
    weight: isUf ? UF_BORDER_WEIGHT : 1.2,
    opacity: 1,
    color: isUf ? UF_BORDER_COLOR : "#ffffff",
    dashArray: "",
    // Mais transparente que no explorador de malhas (0.7) para ruas e escolas continuarem visíveis
    fillOpacity: 0.3,
  };
}

const highlightStyle = {
  weight: 3,
  color: "#1e3a8a",
  dashArray: "",
  fillOpacity: 0.45,
};

// ============================================================================
// PASSO 7: Interatividade (Hover, Clique, Painel de Detalhes)
// ============================================================================
const LAYER_ORDER = ["pais", "regioes", "uf", "municipios"];

// Camadas GeoJSON atualmente combinadas no mapa (chave -> { leafletLayer, ...métricas })
const activeLayers = {};

const detailsContainer = document.getElementById("feature-details");
const loadingIndicator = document.getElementById("loading-indicator");
const basemapSelect = document.getElementById("basemap-select");
const zoomSlider = document.getElementById("zoom-slider");
const toggleGrid = document.getElementById("toggle-grid");
const toggleAutoLod = document.getElementById("toggle-auto-lod");

const layerCheckboxes = {};
LAYER_ORDER.forEach((key) => {
  layerCheckboxes[key] = document.getElementById(`chk-layer-${key}`);
});

function updateDetailsPanel(props) {
  if (!props) {
    detailsContainer.innerHTML = '<div class="empty-state">Nenhuma área selecionada</div>';
    return;
  }

  const nome = props.nome || props.nm_mun || props.nm_uf || "Brasil";
  const codigo = props.codarea || props.cd_mun || props.cd_uf || "-";
  const uf = props.sigla_uf || props.sigla || "-";
  const regiao = props.nm_regiao || props.nome || "-";
  const area = props.AREA_KM2 ? `${Number(props.AREA_KM2).toLocaleString("pt-BR")} km²` : "-";

  let html = `
    <table class="detail-table">
      <tr><td class="label">Nome:</td><td class="value"><strong>${nome}</strong></td></tr>
      <tr><td class="label">Código IBGE:</td><td class="value">${codigo}</td></tr>
  `;

  if (props.sigla_uf || (props.sigla && props.sigla.length === 2)) {
    html += `<tr><td class="label">UF:</td><td class="value">${uf}</td></tr>`;
  }

  if (props.nm_regiao) {
    html += `<tr><td class="label">Região:</td><td class="value">${regiao}</td></tr>`;
  }

  if (props.AREA_KM2) {
    html += `<tr><td class="label">Área:</td><td class="value">${area}</td></tr>`;
  }

  html += `</table>`;
  detailsContainer.innerHTML = html;
}

function onEachFeature(feature, layer, layerKey) {
  const props = feature.properties || {};
  const label = props.nome || props.codarea || "Brasil";

  layer.bindTooltip(label, {
    permanent: false,
    direction: "auto",
    className: "leaflet-tooltip-custom",
  });

  layer.on({
    mouseover: function (e) {
      const target = e.target;
      target.setStyle(highlightStyle);
      target.bringToFront();
      updateDetailsPanel(props);
    },
    mouseout: function (e) {
      e.target.setStyle(getStyle(feature, layerKey));
    },
    click: function (e) {
      map.fitBounds(e.target.getBounds(), { padding: [20, 20] });
      updateDetailsPanel(props);
    },
  });
}

// ============================================================================
// PASSO 8: Carregamento de Dados GeoJSON e Combinação de Camadas Ativas
// ============================================================================
// Cache em memória para os dados GeoJSON (evita requisições repetidas na rede)
const geoJsonCache = {};

function renderActiveLayersPanel() {
  const panel = document.getElementById("active-layers-panel");
  if (!panel) return;

  const activeKeys = LAYER_ORDER.filter((key) => activeLayers[key]);

  if (activeKeys.length === 0) {
    panel.innerHTML = '<div class="empty-state">Nenhuma malha selecionada</div>';
    return;
  }

  panel.innerHTML = activeKeys
    .map((key) => {
      const meta = GEOJSON_METADATA[key];
      const entry = activeLayers[key];
      const sizeText = entry.payloadSizeBytes
        ? `${(entry.payloadSizeBytes / 1024).toFixed(1)} KB`
        : meta.sizeEstimate;
      const timeText = entry.fromCache
        ? "cache local"
        : (entry.downloadDurationMs ? `${entry.downloadDurationMs.toFixed(0)} ms` : "-");

      return `
        <div class="active-layer-chip">
          <div class="active-layer-chip-header">
            <span class="active-layer-name">${meta.description}</span>
            <span class="badge-count">${entry.featuresCount} feições</span>
          </div>
          <div class="active-layer-meta">
            <code>${meta.fileName}</code> · ${sizeText} · ${timeText}
          </div>
        </div>
      `;
    })
    .join("");
}

/**
 * Garante a ordem visual das camadas combinadas: País (base) → Regiões → UF → Municípios (topo).
 */
function reorderActiveLayers() {
  LAYER_ORDER.forEach((key) => {
    const entry = activeLayers[key];
    if (!entry) return;
    if (!map.hasLayer(entry.leafletLayer)) {
      entry.leafletLayer.addTo(map);
    }
    entry.leafletLayer.bringToFront();
  });

  syncUfBoundaryOverlay();
}

// Camada exclusiva de contorno das UFs (sem preenchimento), sempre mantida acima das
// demais — inclusive dos Municípios — para que o "perfil" estadual nunca se perca.
let ufBoundaryLayer = null;

function syncUfBoundaryOverlay() {
  const shouldShow = Boolean(activeLayers.uf) && Boolean(geoJsonCache.uf);

  if (!shouldShow) {
    if (ufBoundaryLayer && map.hasLayer(ufBoundaryLayer)) {
      map.removeLayer(ufBoundaryLayer);
    }
    return;
  }

  if (!ufBoundaryLayer) {
    ufBoundaryLayer = L.geoJSON(geoJsonCache.uf.data, {
      interactive: false, // deixa hover/clique passarem para a camada de baixo (ex.: Municípios)
      style: () => ({
        fillOpacity: 0,
        weight: UF_BORDER_WEIGHT,
        color: UF_BORDER_COLOR,
        opacity: 0.9,
      }),
    });
  }

  if (!map.hasLayer(ufBoundaryLayer)) {
    ufBoundaryLayer.addTo(map);
  }
  ufBoundaryLayer.bringToFront();
}

async function addLayerToMap(layerKey, shouldFitBounds = false) {
  const meta = GEOJSON_METADATA[layerKey];
  if (!meta || activeLayers[layerKey]) return;

  loadingIndicator.classList.remove("hidden");
  const startTime = performance.now();

  try {
    let geojsonData;
    let payloadSizeBytes;
    let fromCache = false;

    // Verifica se já temos em cache de memória
    if (geoJsonCache[layerKey]) {
      geojsonData = geoJsonCache[layerKey].data;
      payloadSizeBytes = geoJsonCache[layerKey].size;
      fromCache = true;
    } else {
      const response = await fetch(meta.filePath);
      if (!response.ok) {
        throw new Error(`Erro HTTP ${response.status} ao carregar ${meta.filePath}`);
      }

      const payloadText = await response.text();
      payloadSizeBytes = new Blob([payloadText]).size;
      geojsonData = JSON.parse(payloadText);

      // Armazena no cache
      geoJsonCache[layerKey] = {
        data: geojsonData,
        size: payloadSizeBytes,
      };
    }

    const downloadDurationMs = performance.now() - startTime;

    const leafletLayer = L.geoJSON(geojsonData, {
      style: (feature) => getStyle(feature, layerKey),
      onEachFeature: (feature, layer) => onEachFeature(feature, layer, layerKey),
    });

    activeLayers[layerKey] = {
      leafletLayer,
      featuresCount: geojsonData.features ? geojsonData.features.length : meta.featuresExpected,
      downloadDurationMs,
      payloadSizeBytes,
      fromCache,
    };

    reorderActiveLayers();

    if (shouldFitBounds) {
      map.fitBounds(leafletLayer.getBounds(), { padding: [10, 10] });
    }

    renderActiveLayersPanel();
    updateTilePyramidStats();
  } catch (error) {
    console.error("Falha ao carregar a malha:", error);
    alert(`Não foi possível carregar os dados: ${error.message}`);
    const checkbox = layerCheckboxes[layerKey];
    if (checkbox) checkbox.checked = false;
  } finally {
    loadingIndicator.classList.add("hidden");
  }
}

function removeLayerFromMap(layerKey) {
  const entry = activeLayers[layerKey];
  if (!entry) return;

  map.removeLayer(entry.leafletLayer);
  delete activeLayers[layerKey];
  syncUfBoundaryOverlay();
  renderActiveLayersPanel();
}

/**
 * Ativa exclusivamente a malha indicada (usado pelo Auto-Recorte por Zoom),
 * desmarcando/removendo as demais e sincronizando os checkboxes da barra lateral.
 */
function setExclusiveLayer(targetLayerKey) {
  LAYER_ORDER.forEach((key) => {
    const checkbox = layerCheckboxes[key];
    const shouldBeOn = key === targetLayerKey;

    if (checkbox) checkbox.checked = shouldBeOn;

    if (shouldBeOn && !activeLayers[key]) {
      addLayerToMap(key);
    } else if (!shouldBeOn && activeLayers[key]) {
      removeLayerFromMap(key);
    }
  });
}

// ============================================================================
// PASSO 9: Auto-Recorte por Zoom (Level of Detail - LOD)
// ============================================================================
let autoLodCurrentKey = null;

function handleAutoLodByZoom() {
  if (!toggleAutoLod || !toggleAutoLod.checked) return;

  const zoom = Math.round(map.getZoom());
  let targetLayerKey = "pais";

  // Mapeamento pedagógico de Escala Territorial por Nível de Zoom
  if (zoom <= 3) {
    targetLayerKey = "pais";        // Z 0..3: Contorno Nacional
  } else if (zoom === 4) {
    targetLayerKey = "regioes";     // Z 4: 5 Grandes Regiões
  } else if (zoom >= 5 && zoom <= 7) {
    targetLayerKey = "uf";          // Z 5..7: 27 Unidades da Federação
  } else if (zoom >= 8) {
    targetLayerKey = "municipios";  // Z 8+: 5.571 Municípios
  }

  if (targetLayerKey !== autoLodCurrentKey) {
    autoLodCurrentKey = targetLayerKey;
    setExclusiveLayer(targetLayerKey);
  }
}

// ============================================================================
// PASSO 10: Eventos e Sincronização
// ============================================================================

map.on("zoomend moveend", () => {
  updateTilePyramidStats();
});

map.on("zoomend", () => {
  handleAutoLodByZoom();
});

if (zoomSlider) {
  zoomSlider.addEventListener("input", (e) => {
    map.setZoom(Number(e.target.value));
  });
}

document.querySelectorAll(".btn-preset").forEach((button) => {
  button.addEventListener("click", () => {
    const targetZoom = Number(button.dataset.zoom);
    map.setZoom(targetZoom);
  });
});

if (toggleGrid) {
  toggleGrid.addEventListener("change", (e) => {
    if (e.target.checked) {
      map.addLayer(debugGridLayer);
    } else {
      map.removeLayer(debugGridLayer);
    }
  });
}

if (toggleAutoLod) {
  toggleAutoLod.addEventListener("change", (e) => {
    if (e.target.checked) {
      autoLodCurrentKey = null; // força a resincronização com o zoom atual
      handleAutoLodByZoom();
    }
  });
}

if (basemapSelect) {
  basemapSelect.addEventListener("change", (e) => {
    setBasemap(e.target.value);
  });
}

// Se o usuário marcar/desmarcar uma malha manualmente, desativa o auto-LOD
LAYER_ORDER.forEach((key) => {
  const checkbox = layerCheckboxes[key];
  if (!checkbox) return;

  checkbox.addEventListener("change", (e) => {
    if (toggleAutoLod) toggleAutoLod.checked = false;
    autoLodCurrentKey = null;

    if (e.target.checked) {
      addLayerToMap(key);
    } else {
      removeLayerFromMap(key);
    }
  });
});

// Inicializações da Aplicação
setBasemap("carto-light");
handleAutoLodByZoom(); // Inicia carregando o recorte correspondente ao zoom inicial
updateTilePyramidStats();


// ============================================================================
// PASSO 11: Camada de Escolas (Censo Escolar 2024 + CNEFE 2022)
// ============================================================================
// Os dados vêm de web/data/escolas/, gerados por
// scripts/commands/escolas_mapa__gerar_dados_web.py (um JSON leve por UF).
//
// Desempenho: em vez de um elemento DOM por escola, as escolas são indexadas
// pelo Supercluster e, a cada movimento do mapa, só o que está na tela é
// desenhado - clusters numerados (poucos, como marcadores HTML) e escolas
// individuais (muitas, como círculos em um único <canvas>).
const ESCOLAS_INDICE_URL = "data/escolas/indice.json";

// Supercluster para de agrupar acima deste zoom: de Z=14 em diante cada escola aparece sozinha
const ESCOLAS_ZOOM_MAX_CLUSTER = 13;

const REDE_ENSINO = {
  "1": { nome: "Federal", cor: "#1e3a8a" },
  "2": { nome: "Estadual", cor: "#16a34a" },
  "3": { nome: "Municipal", cor: "#ea580c" },
  "4": { nome: "Privada", cor: "#9333ea" },
};

// Camadas de confiança do ETL (docs/06-georeferenciamento-escolas.org)
const CONFIANCA_GEO = {
  alta: { nome: "Alta (município + CEP + número)", cor: "#15803d" },
  media: { nome: "Média (município + CEP)", cor: "#d4a106" },
  baixa: { nome: "Baixa (nome no município)", cor: "#dc2626" },
};

const LOCALIZACAO = { "1": "Urbana", "2": "Rural" };

const SITUACAO_FUNCIONAMENTO = {
  "1": "Em atividade",
  "2": "Paralisada",
  "3": "Extinta (no ano)",
  "4": "Extinta (anos anteriores)",
};

// Significado de NV_GEO_COORD segundo o dicionário do CNEFE 2022 - ainda não
// conferido no .xls oficial neste projeto (ver pendências em docs/06).
const CNEFE_NIVEL_COORD = {
  "1": "Endereço - coordenada original do Censo 2022",
  "2": "Endereço - coordenada modificada",
  "3": "Endereço - coordenada estimada",
  "4": "Face de quadra",
  "5": "Localidade",
  "6": "Setor censitário",
};

// Filtros da barra lateral; "padrao" lista as opções marcadas ao abrir a página
const ESCOLAS_FILTROS = [
  { campo: "TP_DEPENDENCIA", titulo: "Rede de ensino", opcoes: mapearNomes(REDE_ENSINO) },
  { campo: "STATUS_GEOLOCALIZACAO", titulo: "Confiança da coordenada", opcoes: { alta: "Alta", media: "Média", baixa: "Baixa" } },
  { campo: "TP_LOCALIZACAO", titulo: "Localização", opcoes: LOCALIZACAO },
  { campo: "TP_SITUACAO_FUNCIONAMENTO", titulo: "Situação", opcoes: SITUACAO_FUNCIONAMENTO, padrao: ["1"] },
];

// Tons de um único matiz (ardósia) para os clusters, para não competir com as cores categóricas dos pontos
const CLUSTER_FAIXAS = [
  { ate: 50, tamanho: 30, cor: "#94a3b8" },
  { ate: 500, tamanho: 38, cor: "#64748b" },
  { ate: 5000, tamanho: 46, cor: "#475569" },
  { ate: Infinity, tamanho: 54, cor: "#1e293b" },
];

function mapearNomes(tabela) {
  const resultado = {};
  Object.keys(tabela).forEach((chave) => { resultado[chave] = tabela[chave].nome; });
  return resultado;
}

function escaparHtml(texto) {
  return String(texto ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

map.createPane("escolasPontos").style.zIndex = 610;
map.createPane("escolasClusters").style.zIndex = 620;

const escolasRenderer = L.canvas({ pane: "escolasPontos", padding: 0.5 });
const escolasLayer = L.layerGroup().addTo(map);

let escolasIndice = null;       // conteúdo de indice.json
const escolasPorUf = {};        // uf -> [escola, ...] (já carregadas)
const ufsAtivas = new Set();    // UFs marcadas na barra lateral
let escolasCluster = null;      // índice Supercluster das escolas que passam nos filtros
let escolasNoFiltro = 0;
let modoCor = "rede";

function corDaEscola(escola) {
  if (modoCor === "confianca") {
    return (CONFIANCA_GEO[escola.STATUS_GEOLOCALIZACAO] || {}).cor || "#64748b";
  }
  return (REDE_ENSINO[escola.TP_DEPENDENCIA] || {}).cor || "#64748b";
}

// ---------------------------------------------------------------------------
// Carregamento dos dados
// ---------------------------------------------------------------------------
async function carregarIndiceEscolas() {
  const container = document.getElementById("escolas-ufs");
  try {
    const resposta = await fetch(ESCOLAS_INDICE_URL);
    if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
    escolasIndice = await resposta.json();
  } catch (erro) {
    console.error("Falha ao carregar o índice de escolas:", erro);
    container.innerHTML = `<div class="empty-state">Índice de escolas não encontrado (${escaparHtml(ESCOLAS_INDICE_URL)}). Rode scripts/commands/escolas_mapa__gerar_dados_web.py.</div>`;
    return;
  }

  const ufs = Object.keys(escolasIndice.ufs).sort();
  container.innerHTML = ufs
    .map((uf) => {
      const info = escolasIndice.ufs[uf];
      const mb = (info.tamanho_bytes / 1e6).toFixed(1);
      return `
        <label class="checkbox-label" title="${info.no_mapa.toLocaleString("pt-BR")} de ${info.total_escolas.toLocaleString("pt-BR")} escolas têm coordenada">
          <input type="checkbox" data-escolas-uf="${uf}"> ${uf}
          <span class="escolas-uf-meta">${info.no_mapa.toLocaleString("pt-BR")} escolas · ${mb} MB</span>
        </label>`;
    })
    .join("");

  container.querySelectorAll("input[data-escolas-uf]").forEach((checkbox) => {
    checkbox.addEventListener("change", (e) => alternarUf(e.target.dataset.escolasUf, e.target.checked));
  });

  // Com uma única UF disponível (piloto), já a exibe ao abrir a página
  if (ufs.length === 1) {
    container.querySelector("input[data-escolas-uf]").checked = true;
    alternarUf(ufs[0], true);
  }
}

async function carregarEscolasDaUf(uf) {
  if (escolasPorUf[uf]) return escolasPorUf[uf];

  const resposta = await fetch(escolasIndice.ufs[uf].arquivo);
  if (!resposta.ok) throw new Error(`HTTP ${resposta.status} ao carregar ${escolasIndice.ufs[uf].arquivo}`);
  const dados = await resposta.json();

  // Converte as linhas compactas em objetos e já prepara o ponto GeoJSON usado pelo Supercluster
  escolasPorUf[uf] = dados.escolas.map((linha) => {
    const escola = { SG_UF: uf };
    dados.campos.forEach((campo, i) => { escola[campo] = linha[i]; });
    escola.TP_DEPENDENCIA = String(escola.TP_DEPENDENCIA);
    escola.TP_LOCALIZACAO = String(escola.TP_LOCALIZACAO);
    escola.TP_SITUACAO_FUNCIONAMENTO = String(escola.TP_SITUACAO_FUNCIONAMENTO);
    escola.ponto = {
      type: "Feature",
      properties: { escola },
      geometry: { type: "Point", coordinates: [escola.LONGITUDE, escola.LATITUDE] },
    };
    return escola;
  });
  return escolasPorUf[uf];
}

async function alternarUf(uf, ligar) {
  if (!ligar) {
    ufsAtivas.delete(uf);
    reconstruirIndiceEscolas();
    return;
  }

  loadingIndicator.textContent = `Carregando escolas (${uf})...`;
  loadingIndicator.classList.remove("hidden");
  try {
    const escolas = await carregarEscolasDaUf(uf);
    ufsAtivas.add(uf);
    reconstruirIndiceEscolas();
    const limites = L.latLngBounds(escolas.map((e) => [e.LATITUDE, e.LONGITUDE]));
    map.fitBounds(limites, { padding: [20, 20] });
  } catch (erro) {
    console.error("Falha ao carregar escolas:", erro);
    alert(`Não foi possível carregar as escolas de ${uf}: ${erro.message}`);
    const checkbox = document.querySelector(`input[data-escolas-uf="${uf}"]`);
    if (checkbox) checkbox.checked = false;
  } finally {
    loadingIndicator.classList.add("hidden");
    loadingIndicator.textContent = "Carregando malha...";
  }
}

// ---------------------------------------------------------------------------
// Filtros e índice espacial
// ---------------------------------------------------------------------------
function renderFiltrosEscolas() {
  const container = document.getElementById("escolas-filtros");
  container.innerHTML = ESCOLAS_FILTROS
    .map((filtro) => {
      const opcoes = Object.keys(filtro.opcoes)
        .map((valor) => {
          const marcado = !filtro.padrao || filtro.padrao.includes(valor);
          return `<label class="checkbox-label"><input type="checkbox" data-filtro-campo="${filtro.campo}" value="${valor}" ${marcado ? "checked" : ""}> ${filtro.opcoes[valor]}</label>`;
        })
        .join("");
      return `<span class="escolas-filtro-titulo">${filtro.titulo}</span><div class="escolas-filtro-grupo">${opcoes}</div>`;
    })
    .join("");

  container.querySelectorAll("input[data-filtro-campo]").forEach((checkbox) => {
    checkbox.addEventListener("change", reconstruirIndiceEscolas);
  });
}

function lerFiltrosEscolas() {
  const selecionados = {};
  ESCOLAS_FILTROS.forEach((filtro) => { selecionados[filtro.campo] = new Set(); });
  document.querySelectorAll("input[data-filtro-campo]:checked").forEach((checkbox) => {
    selecionados[checkbox.dataset.filtroCampo].add(checkbox.value);
  });
  return selecionados;
}

function reconstruirIndiceEscolas() {
  const filtros = lerFiltrosEscolas();
  const campos = Object.keys(filtros);
  const pontos = [];

  ufsAtivas.forEach((uf) => {
    escolasPorUf[uf].forEach((escola) => {
      if (campos.every((campo) => filtros[campo].has(escola[campo]))) {
        pontos.push(escola.ponto);
      }
    });
  });

  escolasCluster = new Supercluster({ radius: 60, maxZoom: ESCOLAS_ZOOM_MAX_CLUSTER });
  escolasCluster.load(pontos);
  escolasNoFiltro = pontos.length;

  renderEscolas();
  renderResumoEscolas();
}

// ---------------------------------------------------------------------------
// Desenho: só o que está visível na tela
// ---------------------------------------------------------------------------
function renderEscolas() {
  escolasLayer.clearLayers();
  if (!escolasCluster || escolasNoFiltro === 0) return;

  const limites = map.getBounds();
  const itens = escolasCluster.getClusters(
    [limites.getWest(), limites.getSouth(), limites.getEast(), limites.getNorth()],
    Math.round(map.getZoom())
  );

  itens.forEach((item) => {
    const [lng, lat] = item.geometry.coordinates;
    const camada = item.properties.cluster
      ? criarMarcadorCluster(item, lat, lng)
      : criarPontoEscola(item.properties.escola, lat, lng);
    escolasLayer.addLayer(camada);
  });
}

function criarMarcadorCluster(item, lat, lng) {
  const total = item.properties.point_count;
  const faixa = CLUSTER_FAIXAS.find((f) => total <= f.ate);
  const marcador = L.marker([lat, lng], {
    pane: "escolasClusters",
    icon: L.divIcon({
      className: "",
      iconSize: [faixa.tamanho, faixa.tamanho],
      html: `<div class="escolas-cluster" style="width:${faixa.tamanho}px;height:${faixa.tamanho}px;background:${faixa.cor}">${item.properties.point_count_abbreviated}</div>`,
    }),
  });

  marcador.bindTooltip(`${total.toLocaleString("pt-BR")} escolas · clique para aproximar`, {
    direction: "top",
    className: "leaflet-tooltip-custom",
  });
  marcador.on("click", () => {
    const zoomExpansao = escolasCluster.getClusterExpansionZoom(item.properties.cluster_id);
    map.setView([lat, lng], Math.min(zoomExpansao, map.getMaxZoom()));
  });
  return marcador;
}

function criarPontoEscola(escola, lat, lng) {
  const ponto = L.circleMarker([lat, lng], {
    renderer: escolasRenderer,
    radius: 6,
    color: "#ffffff",
    weight: 1.5,
    fillColor: corDaEscola(escola),
    fillOpacity: 0.95,
  });

  const rede = (REDE_ENSINO[escola.TP_DEPENDENCIA] || {}).nome || "-";
  ponto.bindTooltip(`<strong>${escaparHtml(escola.NO_ENTIDADE)}</strong><br>${rede}`, {
    direction: "top",
    className: "leaflet-tooltip-custom",
  });

  // O popup pertence ao mapa (não ao ponto): os pontos são recriados a cada
  // movimento do mapa, e um popup preso a eles fecharia sozinho ao arrastar.
  ponto.on("click", () => {
    L.popup({ maxWidth: 360, className: "escolas-popup" })
      .setLatLng([lat, lng])
      .setContent(htmlEscola(escola, true))
      .openOn(map);
    detailsContainer.innerHTML = htmlEscola(escola, false);
  });
  return ponto;
}

function htmlEscola(escola, comTitulo) {
  const lat = escola.LATITUDE;
  const lng = escola.LONGITUDE;
  const confianca = CONFIANCA_GEO[escola.STATUS_GEOLOCALIZACAO] || {};
  const nivel = escola.CNEFE_NV_GEO_COORD != null
    ? `${escola.CNEFE_NV_GEO_COORD} - ${CNEFE_NIVEL_COORD[escola.CNEFE_NV_GEO_COORD] || "desconhecido"}`
    : "-";
  const matriculas = escola.QT_MAT_BAS != null ? escola.QT_MAT_BAS.toLocaleString("pt-BR") : "-";
  const linhas = [
    ["Código INEP", escola.CO_ENTIDADE],
    ["Nome", escola.NO_ENTIDADE],
    ["Rede", (REDE_ENSINO[escola.TP_DEPENDENCIA] || {}).nome],
    ["Localização", LOCALIZACAO[escola.TP_LOCALIZACAO]],
    ["Situação", SITUACAO_FUNCIONAMENTO[escola.TP_SITUACAO_FUNCIONAMENTO]],
    ["Matrículas", matriculas],
    ["Município", `${escola.NO_MUNICIPIO} - ${escola.SG_UF}`],
    ["Endereço (Censo)", escola.ENDERECO_CENSO],
    ["Nome no CNEFE", escola.CNEFE_DSC_ESTABELECIMENTO],
    ["Confiança", confianca.nome || escola.STATUS_GEOLOCALIZACAO],
    ["Nível CNEFE", nivel],
    ["Coordenadas", `${lat.toFixed(6)}, ${lng.toFixed(6)}`],
  ];

  const tabela = linhas
    .map(([rotulo, valor]) => `<tr><td class="label">${rotulo}:</td><td class="value">${escaparHtml(valor || "-")}</td></tr>`)
    .join("");

  return `
    ${comTitulo ? `<h4>🏫 ${escaparHtml(escola.NO_ENTIDADE)}</h4>` : ""}
    <table class="detail-table">${tabela}</table>
    <div class="links mt-2">
      <a href="https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=18/${lat}/${lng}" target="_blank" rel="noopener">OpenStreetMap ↗</a>
      <a href="https://www.google.com/maps?q=${lat},${lng}" target="_blank" rel="noopener">Google Maps ↗</a>
    </div>`;
}

// ---------------------------------------------------------------------------
// Legenda e resumo
// ---------------------------------------------------------------------------
function renderLegendaEscolas() {
  const tabela = modoCor === "confianca" ? CONFIANCA_GEO : REDE_ENSINO;
  document.getElementById("escolas-legenda").innerHTML = Object.values(tabela)
    .map((item) => `<li><span class="legend-color" style="background: ${item.cor};"></span> ${item.nome}</li>`)
    .join("");
}

function renderResumoEscolas() {
  const resumo = document.getElementById("escolas-resumo");
  if (ufsAtivas.size === 0) {
    resumo.innerHTML = '<div class="empty-state">Nenhuma UF selecionada</div>';
    return;
  }

  let total = 0;
  let semCoordenada = 0;
  ufsAtivas.forEach((uf) => {
    const info = escolasIndice.ufs[uf];
    total += info.total_escolas;
    semCoordenada += info.total_escolas - info.no_mapa;
  });

  resumo.innerHTML = `
    <div class="math-row">
      <span class="math-label">No mapa (com filtros):</span>
      <span class="math-value highlight-coords">${escolasNoFiltro.toLocaleString("pt-BR")}</span>
    </div>
    <div class="math-row">
      <span class="math-label">Escolas no Censo (UFs marcadas):</span>
      <span class="math-value">${total.toLocaleString("pt-BR")}</span>
    </div>
    <div class="math-row" title="Status ambiguo ou sem_correspondencia no ETL: estas escolas não aparecem no mapa">
      <span class="math-label">Sem coordenada (fora do mapa):</span>
      <span class="math-value">${semCoordenada.toLocaleString("pt-BR")}</span>
    </div>`;
}

// ---------------------------------------------------------------------------
// Eventos da camada de escolas
// ---------------------------------------------------------------------------
map.on("moveend", renderEscolas);

document.querySelectorAll('input[name="escolas-cor"]').forEach((radio) => {
  radio.addEventListener("change", (e) => {
    modoCor = e.target.value;
    renderLegendaEscolas();
    renderEscolas();
  });
});

renderFiltrosEscolas();
renderLegendaEscolas();
renderResumoEscolas();
carregarIndiceEscolas();
