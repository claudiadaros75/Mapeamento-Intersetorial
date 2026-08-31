/**
 * ============================================================================
 * Explorador de Malhas do IBGE com Leaflet.js
 * ============================================================================
 * 
 * Este script demonstra os conceitos fundamentais da cartografia web:
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
debugGridLayer.addTo(map);

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

function getFeatureColor(properties) {
  if (!properties) return "#3b82f6";
  const regId = properties.cd_regiao || properties.sigla_regiao || properties.sigla || properties.nome;
  return REGION_COLORS[regId] || "#60a5fa";
}

function getStyle(feature) {
  return {
    fillColor: getFeatureColor(feature.properties),
    weight: 1.2,
    opacity: 1,
    color: "#ffffff",
    dashArray: "",
    fillOpacity: 0.7,
  };
}

const highlightStyle = {
  weight: 3,
  color: "#1e3a8a",
  dashArray: "",
  fillOpacity: 0.85,
};

// ============================================================================
// PASSO 7: Interatividade (Hover, Clique, Painel de Detalhes)
// ============================================================================
let currentGeoJsonLayer = null;
let currentLayerKey = "uf";

const detailsContainer = document.getElementById("feature-details");
const loadingIndicator = document.getElementById("loading-indicator");
const layerSelect = document.getElementById("layer-select");
const basemapSelect = document.getElementById("basemap-select");
const zoomSlider = document.getElementById("zoom-slider");
const toggleGrid = document.getElementById("toggle-grid");
const toggleAutoLod = document.getElementById("toggle-auto-lod");

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

function onEachFeature(feature, layer) {
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
      if (currentGeoJsonLayer) {
        currentGeoJsonLayer.resetStyle(e.target);
      }
    },
    click: function (e) {
      map.fitBounds(e.target.getBounds(), { padding: [20, 20] });
      updateDetailsPanel(props);
    },
  });
}

// ============================================================================
// PASSO 8: Carregamento de Dados GeoJSON e Atualização do Inspetor
// ============================================================================
// Cache em memória para os dados GeoJSON (evita requisições repetidas na rede)
const geoJsonCache = {};

function updateGeoJsonInspector(layerKey, featuresCount, downloadDurationMs, payloadSizeBytes, fromCache = false) {
  const meta = GEOJSON_METADATA[layerKey];
  if (!meta) return;

  const fileEl = document.getElementById("info-geojson-file");
  const featuresEl = document.getElementById("info-geojson-features");
  const sizeEl = document.getElementById("info-geojson-size");
  const timeEl = document.getElementById("info-geojson-time");
  const apiEl = document.getElementById("info-ibge-api-url");

  if (fileEl) fileEl.textContent = meta.fileName;
  if (featuresEl) featuresEl.textContent = `${featuresCount || meta.featuresExpected} feições`;
  if (sizeEl) {
    sizeEl.textContent = payloadSizeBytes
      ? `${(payloadSizeBytes / 1024).toFixed(1)} KB`
      : meta.sizeEstimate;
  }
  if (timeEl) {
    timeEl.textContent = fromCache
      ? "Cache local (0 ms)"
      : (downloadDurationMs ? `${downloadDurationMs.toFixed(0)} ms` : "-");
  }
  if (apiEl) apiEl.textContent = meta.ibgeApiUrl;
}

async function loadLayer(layerKey, shouldFitBounds = false) {
  const meta = GEOJSON_METADATA[layerKey];
  if (!meta) return;

  currentLayerKey = layerKey;
  if (layerSelect) layerSelect.value = layerKey;

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

    if (currentGeoJsonLayer) {
      map.removeLayer(currentGeoJsonLayer);
    }

    currentGeoJsonLayer = L.geoJSON(geojsonData, {
      style: getStyle,
      onEachFeature: onEachFeature,
    });

    currentGeoJsonLayer.addTo(map);

    if (shouldFitBounds) {
      map.fitBounds(currentGeoJsonLayer.getBounds(), { padding: [10, 10] });
    }

    updateGeoJsonInspector(
      layerKey,
      geojsonData.features ? geojsonData.features.length : meta.featuresExpected,
      downloadDurationMs,
      payloadSizeBytes,
      fromCache
    );
    updateTilePyramidStats();

  } catch (error) {
    console.error("Falha ao carregar a malha:", error);
    alert(`Não foi possível carregar os dados: ${error.message}`);
  } finally {
    loadingIndicator.classList.add("hidden");
  }
}

// ============================================================================
// PASSO 9: Auto-Recorte por Zoom (Level of Detail - LOD)
// ============================================================================
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

  if (targetLayerKey !== currentLayerKey) {
    // Carrega a camada correspondente mantendo o ponto de vista atual do usuário
    loadLayer(targetLayerKey, false);
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
      handleAutoLodByZoom();
    }
  });
}

if (basemapSelect) {
  basemapSelect.addEventListener("change", (e) => {
    setBasemap(e.target.value);
  });
}

// Se o usuário escolher um recorte manualmente, desativa temporariamente o auto-LOD
if (layerSelect) {
  layerSelect.addEventListener("change", (e) => {
    if (toggleAutoLod) toggleAutoLod.checked = false;
    loadLayer(e.target.value, false);
  });
}

// Inicializações da Aplicação
setBasemap("carto-light");
handleAutoLodByZoom(); // Inicia carregando o recorte correspondente ao zoom inicial
updateTilePyramidStats();

