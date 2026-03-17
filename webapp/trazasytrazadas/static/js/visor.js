/**
 * Lógica de interfaz del visor cartográfico.
 *
 * Este archivo controla la selección de un área sobre Leaflet, la petición al
 * backend para resolver la mejor ortofoto PNOA disponible, la visualización
 * de la cuadrícula resultante y la descarga de teselas individuales o en ZIP.
 *
 * Autor: Marcos Zamorano Lasso
 * Versión: 0.1
 */

document.addEventListener("DOMContentLoaded", () => {
  const CFG = window.VISOR_APP || {};
  const URLS = CFG.urls || {};
  const DEFAULTS = Object.assign(
    {
      center: [40.4168, -3.7038],
      zoom: 6,
      minZoom: 5,
      maxZoom: 21,
      tileWarningThreshold: 64,
      tileListSoftLimit: 80,
      maxDownloadBatch: 256,
    },
    CFG.defaults || {}
  );
  const I18N = Object.assign(
    {
      selectionPending: "Haz dos clics sobre el mapa para definir el rectángulo de trabajo.",
      selectionReady: "Área seleccionada: {width} m × {height} m aprox.",
      selectionClickSecond: "Primer punto fijado. Haz clic para marcar la esquina opuesta.",
      sourcePending: "Pendiente de generación",
      downloadsPending: "Aún no se ha generado ninguna cuadrícula.",
      downloadsReady: "{count} teselas a {resolution} m/px usando {source}.",
      downloadsPartialList: "Se muestran las primeras {count} teselas en la lista. Usa el ZIP para descargar el conjunto completo.",
      tileLabel: "Tesela {row}-{col}",
      download: "Descargar",
      downloadZip: "Descargar ZIP",
      gridGenerationError: "No se ha podido generar la cuadrícula.",
      largeGridWarning: "La cuadrícula contiene muchas teselas y puede implicar una descarga pesada.",
      fallbackWarning: "La resolución solicitada no está disponible en la zona. Se ha aplicado fallback automático.",
      resolutionWarning: "La ortofoto seleccionada no alcanza la resolución pedida para esa zona.",
      statusLoading: "Calculando cobertura y cuadrícula...",
      statusReset: "Selección reiniciada. Elige dos puntos para crear un nuevo rectángulo.",
      zipPreparing: "Preparando ZIP de teselas...",
      zipReady: "Se ha iniciado la descarga del ZIP.",
      zipError: "No se ha podido generar el ZIP.",
      tooManyPoints: "Ya existe una selección activa. Usa «Reset selección» para empezar de nuevo.",
      emptyList: "Genera primero la cuadrícula para obtener las teselas descargables.",
      activePreview: "Capa mostrada: {source} · resolución efectiva {resolution} m/px.",
      previewLatest: "La base visible muestra OpenStreetMap y PNOA de máxima actualidad.",
      coverageError: "No se ha encontrado cobertura PNOA adecuada para el área seleccionada.",
      serverError: "La operación no se pudo completar correctamente.",
      gridBounds: "Rectángulo: {south}, {west} ↔ {north}, {east}",
      tilesCount: "{count} teselas · tamaño por tesela hasta {size} px.",
      selectedSource: "Fuente: {source} ({service})",
      downloadingTile: "Descargando {tile}...",
    },
    CFG.i18n || {}
  );

  const mapEl = document.getElementById("visor-map");
  const alertsEl = document.getElementById("visor-alerts");
  const selectionSummaryEl = document.getElementById("selection-summary");
  const sourceSummaryEl = document.getElementById("source-summary");
  const downloadsSummaryEl = document.getElementById("downloads-summary");
  const resolutionSelect = document.getElementById("resolution-select");
  const tileSizeSelect = document.getElementById("tile-size-select");
  const generateGridBtn = document.getElementById("generate-grid-btn");
  const resetSelectionBtn = document.getElementById("reset-selection-btn");
  const downloadAllBtn = document.getElementById("download-all-btn");
  const downloadListEl = document.getElementById("download-list");

  const map = L.map(mapEl, {
    center: DEFAULTS.center,
    zoom: DEFAULTS.zoom,
    minZoom: DEFAULTS.minZoom,
    maxZoom: DEFAULTS.maxZoom,
  });

  const osmLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  const pnoaLatestLayer = L.tileLayer(
    "https://www.ign.es/wmts/pnoa-ma?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=OI.OrthoimageCoverage&STYLE=default&TILEMATRIXSET=GoogleMapsCompatible&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg",
    {
      maxZoom: DEFAULTS.maxZoom,
      attribution: "PNOA máxima actualidad (IGN/CNIG)",
    }
  ).addTo(map);

  const layerControl = L.control.layers(
    {
      OpenStreetMap: osmLayer,
      "PNOA máxima actualidad": pnoaLatestLayer,
    },
    {},
    { collapsed: true }
  ).addTo(map);

  const previewGroup = L.layerGroup().addTo(map);
  const markersGroup = L.layerGroup().addTo(map);
  const selectionGroup = L.layerGroup().addTo(map);
  const gridGroup = L.layerGroup().addTo(map);

  let selectedPoints = [];
  let selectionBounds = null;
  let selectionRectangle = null;
  let activePreviewLayer = null;
  let currentPlan = null;

  function formatTemplate(template, values) {
    return Object.keys(values).reduce(
      (acc, key) => acc.replaceAll(`{${key}}`, String(values[key])),
      template
    );
  }

  function roundCoord(value, digits = 6) {
    return Number(value).toFixed(digits);
  }

  function setSelectionSummary(message) {
    if (selectionSummaryEl) selectionSummaryEl.textContent = message;
  }

  function setSourceSummary(message) {
    if (sourceSummaryEl) sourceSummaryEl.textContent = message;
  }

  function setDownloadsSummary(message) {
    if (downloadsSummaryEl) downloadsSummaryEl.textContent = message;
  }

  function clearAlerts() {
    if (alertsEl) alertsEl.innerHTML = "";
  }

  function addAlert(kind, message) {
    if (!alertsEl) return;
    const div = document.createElement("div");
    div.className = `alert shadow-sm ${kind}`;
    div.innerHTML = `<span class="text-sm">${message}</span>`;
    alertsEl.appendChild(div);
  }

  function setEmptyDownloadsList() {
    if (!downloadListEl) return;
    downloadListEl.innerHTML = `<div class="text-sm opacity-70">${I18N.emptyList}</div>`;
    if (downloadAllBtn) downloadAllBtn.disabled = true;
  }

  function resetGridState() {
    gridGroup.clearLayers();
    previewGroup.clearLayers();
    if (activePreviewLayer) {
      layerControl.removeLayer(activePreviewLayer);
      activePreviewLayer = null;
    }
    currentPlan = null;
    setSourceSummary(I18N.sourcePending);
    setDownloadsSummary(I18N.downloadsPending);
    setEmptyDownloadsList();
  }

  function resetSelection() {
    selectedPoints = [];
    selectionBounds = null;
    markersGroup.clearLayers();
    selectionGroup.clearLayers();
    selectionRectangle = null;
    clearAlerts();
    resetGridState();
    setSelectionSummary(I18N.statusReset);
  }

  function updateSelectionSummaryFromBounds(bounds) {
    const sw = bounds.getSouthWest();
    const ne = bounds.getNorthEast();
    const width = map.distance([sw.lat, sw.lng], [sw.lat, ne.lng]);
    const height = map.distance([sw.lat, sw.lng], [ne.lat, sw.lng]);
    setSelectionSummary(
      formatTemplate(I18N.selectionReady, {
        width: Math.round(width),
        height: Math.round(height),
      })
    );
  }

  function buildPayload() {
    if (!selectionBounds) return null;
    const sw = selectionBounds.getSouthWest();
    const ne = selectionBounds.getNorthEast();
    return {
      bbox: {
        south: sw.lat,
        west: sw.lng,
        north: ne.lat,
        east: ne.lng,
      },
      resolution: Number.parseFloat(resolutionSelect.value),
      tile_size: Number.parseInt(tileSizeSelect.value, 10),
    };
  }

  function triggerFileDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  async function downloadSingleTile(tile) {
    addAlert("alert-info", formatTemplate(I18N.downloadingTile, { tile: tile.label }));
    const response = await fetch(tile.download_url, { method: "GET" });
    if (!response.ok) {
      throw new Error(I18N.serverError);
    }
    const blob = await response.blob();
    triggerFileDownload(blob, tile.filename);
  }

  function renderDownloadList(plan) {
    if (!downloadListEl) return;
    downloadListEl.innerHTML = "";

    const visibleTiles = plan.tiles.slice(0, DEFAULTS.tileListSoftLimit);
    visibleTiles.forEach((tile) => {
      const row = document.createElement("div");
      row.className = "flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 rounded-box border border-base-200 bg-base-50 px-3 py-2";

      const meta = document.createElement("div");
      meta.className = "min-w-0";
      meta.innerHTML = `
        <div class="font-semibold text-sm truncate">${tile.label}</div>
        <div class="text-xs opacity-70 truncate">${tile.filename}</div>
      `;

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-sm btn-outline shrink-0";
      btn.textContent = I18N.download;
      btn.addEventListener("click", async () => {
        try {
          await downloadSingleTile(tile);
        } catch (error) {
          clearAlerts();
          addAlert("alert-error", error.message || I18N.serverError);
        }
      });

      row.appendChild(meta);
      row.appendChild(btn);
      downloadListEl.appendChild(row);
    });

    if (plan.tiles.length > visibleTiles.length) {
      const note = document.createElement("div");
      note.className = "text-xs opacity-70";
      note.textContent = formatTemplate(I18N.downloadsPartialList, {
        count: visibleTiles.length,
      });
      downloadListEl.appendChild(note);
    }

    if (downloadAllBtn) {
      downloadAllBtn.disabled = false;
      downloadAllBtn.textContent = I18N.downloadZip;
    }
  }

  function renderPreviewLayer(plan) {
    previewGroup.clearLayers();
    if (activePreviewLayer) {
      layerControl.removeLayer(activePreviewLayer);
      activePreviewLayer = null;
    }

    if (!plan.preview || plan.preview.type !== "wms") {
      setSourceSummary(
        formatTemplate(I18N.activePreview, {
          source: plan.source.label,
          resolution: plan.actual_resolution.toFixed(2),
        })
      );
      return;
    }

    activePreviewLayer = L.tileLayer.wms(plan.preview.url, {
      layers: plan.preview.layer,
      format: "image/jpeg",
      transparent: false,
      version: "1.1.1",
      attribution: plan.source.label,
    });

    layerControl.addOverlay(activePreviewLayer, plan.source.label);
    previewGroup.addLayer(activePreviewLayer);

    setSourceSummary(
      formatTemplate(I18N.activePreview, {
        source: plan.source.label,
        resolution: plan.actual_resolution.toFixed(2),
      })
    );
  }

  function renderGrid(plan) {
    gridGroup.clearLayers();

    plan.tiles.forEach((tile) => {
      const bounds = L.latLngBounds(
        [tile.bounds.south, tile.bounds.west],
        [tile.bounds.north, tile.bounds.east]
      );

      const rect = L.rectangle(bounds, {
        color: "#1d4ed8",
        weight: 1,
        fillOpacity: 0.04,
      });
      rect.bindTooltip(tile.label, { sticky: true });
      rect.addTo(gridGroup);
    });
  }

  async function generateGrid() {
    const payload = buildPayload();
    if (!payload) {
      clearAlerts();
      addAlert("alert-warning", I18N.selectionPending);
      return;
    }

    clearAlerts();
    addAlert("alert-info", I18N.statusLoading);

    try {
      const response = await fetch(URLS.plan, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();
      clearAlerts();

      if (!response.ok) {
        addAlert("alert-error", data.error || I18N.gridGenerationError);
        return;
      }

      currentPlan = data;
      renderPreviewLayer(data);
      renderGrid(data);
      renderDownloadList(data);

      setDownloadsSummary(
        formatTemplate(I18N.downloadsReady, {
          count: data.tile_count,
          resolution: data.actual_resolution.toFixed(2),
          source: data.source.label,
        })
      );

      data.warnings.forEach((warning) => {
        addAlert(`alert-${warning.level || "warning"}`, warning.message);
      });

      if (data.tile_count > DEFAULTS.tileWarningThreshold) {
        addAlert("alert-warning", I18N.largeGridWarning);
      }
    } catch (error) {
      clearAlerts();
      addAlert("alert-error", error.message || I18N.gridGenerationError);
    }
  }

  async function downloadZip() {
    if (!currentPlan) return;

    clearAlerts();
    addAlert("alert-info", I18N.zipPreparing);

    try {
      const response = await fetch(URLS.downloadZip, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          source_id: currentPlan.source.id,
          actual_resolution: currentPlan.actual_resolution,
          tiles: currentPlan.tiles,
        }),
      });

      if (!response.ok) {
        throw new Error(I18N.zipError);
      }

      const disposition = response.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="([^"]+)"/i);
      const filename = match ? match[1] : "visor_tiles.zip";
      const blob = await response.blob();
      triggerFileDownload(blob, filename);
      clearAlerts();
      addAlert("alert-success", I18N.zipReady);
    } catch (error) {
      clearAlerts();
      addAlert("alert-error", error.message || I18N.zipError);
    }
  }

  map.on("click", (event) => {
    if (selectedPoints.length >= 2) {
      clearAlerts();
      addAlert("alert-warning", I18N.tooManyPoints);
      return;
    }

    selectedPoints.push(event.latlng);
    L.marker(event.latlng).addTo(markersGroup);

    if (selectedPoints.length === 1) {
      clearAlerts();
      addAlert("alert-info", I18N.selectionClickSecond);
      return;
    }

    selectionBounds = L.latLngBounds(selectedPoints[0], selectedPoints[1]);
    if (selectionRectangle) {
      selectionGroup.removeLayer(selectionRectangle);
    }

    selectionRectangle = L.rectangle(selectionBounds, {
      color: "#f59e0b",
      weight: 2,
      fillOpacity: 0.15,
    }).addTo(selectionGroup);

    updateSelectionSummaryFromBounds(selectionBounds);
    map.fitBounds(selectionBounds.pad(0.15));
    resetGridState();
  });

  generateGridBtn.addEventListener("click", generateGrid);
  resetSelectionBtn.addEventListener("click", resetSelection);
  downloadAllBtn.addEventListener("click", downloadZip);

  setSelectionSummary(I18N.selectionPending);
  setSourceSummary(I18N.previewLatest);
  setDownloadsSummary(I18N.downloadsPending);
  setEmptyDownloadsList();
});
