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
      fallbackWarning: "La resolución solicitada no está disponible en la zona. Se ha aplicado un ajuste automático.",
      resolutionWarning: "La ortofoto seleccionada no alcanza la resolución pedida para esa zona.",
      statusLoading: "Calculando cobertura y cuadrícula...",
      statusReset: "Selección reiniciada. Elige dos puntos para crear un nuevo rectángulo.",
      zipPreparing: "Preparando ZIP de teselas...",
      zipReady: "Se ha iniciado la descarga del ZIP.",
      zipError: "No se ha podido generar el ZIP.",
      tooManyPoints: "Ya existe una selección activa. Usa «Reiniciar selección» para empezar de nuevo.",
      emptyList: "Genera primero la cuadrícula para obtener las teselas descargables.",
      activePreview: "Capa mostrada: {source} · resolución efectiva {resolution} m/px.",
      previewLatest: "La base visible muestra OpenStreetMap y PNOA de máxima actualidad.",
      coverageError: "No se ha encontrado cobertura PNOA adecuada para el área seleccionada.",
      serverError: "La operación no se pudo completar correctamente.",
      gridBounds: "Rectángulo: {south}, {west} ↔ {north}, {east}",
      tilesCount: "{count} teselas · formato {width} × {height} px.",
      selectedSource: "Fuente: {source} ({service})",
      downloadingTile: "Descargando {tile}...",
      zoneRegistered: "La zona se ha registrado en la colección.",
      restoredZone: "Zona recuperada desde la colección.",
      openCollection: "Abrir colección",
      close: "Cerrar",
      drawMapTraces: "Dibujar trazas",
      mapTracesLoading: "Cargando trazas en el mapa...",
      mapTracesReady: "Trazas dibujadas en el mapa.",
      mapTracesError: "No se han podido dibujar las trazas en el mapa.",
      mapTracesUnavailable: "Las trazas estarán disponibles cuando todas las teselas estén calculadas.",
      mapTraceStatusCompleted: "Trazas calculadas",
      mapTraceStatusProcessing: "Trazas en proceso",
      mapTraceStatusFailed: "Hay trazas con error",
      mapTraceStatusPending: "Trazas pendientes",
    },
    CFG.i18n || {}
  );

  const mapEl = document.getElementById("visor-map");
  const alertsEl = document.getElementById("visor-alerts");
  const selectionSummaryEl = document.getElementById("selection-summary");
  const sourceSummaryEl = document.getElementById("source-summary");
  const downloadsSummaryEl = document.getElementById("downloads-summary");
  const resolutionSelect = document.getElementById("resolution-select");
  const openControlsBtn = document.getElementById("open-controls-btn");
  const controlsModal = document.getElementById("visor-controls-modal");
  const generateGridBtn = document.getElementById("generate-grid-btn");
  const resetSelectionBtn = document.getElementById("reset-selection-btn");
  const downloadAllBtn = document.getElementById("download-all-btn");
  const downloadListEl = document.getElementById("download-list");
  const downloadsSectionEl = document.getElementById("downloads-section");
  const mapTracesPanel = document.getElementById("map-traces-panel");
  const mapTracesCheckbox = document.getElementById("map-traces-checkbox");
  const mapTracesStatus = document.getElementById("map-traces-status");

  const map = L.map(mapEl, {
    center: DEFAULTS.center,
    zoom: DEFAULTS.zoom,
    minZoom: DEFAULTS.minZoom,
    maxZoom: DEFAULTS.maxZoom,
    maxBoundsViscosity: 1.0,
    zoomControl: false,
  });

  const initialMapBounds = map.getBounds();
  map.setMaxBounds(initialMapBounds);
  L.control.zoom({ position: "bottomleft" }).addTo(map);

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
  const traceOverlayGroup = L.layerGroup().addTo(map);

  let selectedPoints = [];
  let selectionBounds = null;
  let selectionRectangle = null;
  let activePreviewLayer = null;
  let currentPlan = null;
  let drawingMapTraces = false;
  const traceOverlayCache = new Map();
  const initialZone = CFG.initialZone || null;

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

  function dismissAlert(alertEl) {
    if (!alertEl) return;
    alertEl.style.transition = "opacity 250ms ease";
    alertEl.style.opacity = "0";
    window.setTimeout(() => alertEl.remove(), 260);
  }

  function scrollToDownloads() {
    if (!downloadsSectionEl) return;
    downloadsSectionEl.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  function addAlert(kind, message) {
    if (!alertsEl) return;

    const div = document.createElement("div");
    div.className = `alert ${kind} shadow-lg max-w-2xl`;

    div.innerHTML = `
      <span class="text-sm sm:text-base">${message}</span>
      <button type="button"
              class="btn btn-sm btn-ghost ml-auto"
              aria-label="${I18N.close}">
        <svg xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            class="w-4 h-4">
          <path d="M6.28 5.22a.75.75 0 0 1 1.06 0L10 7.94l2.66-2.72a.75.75 0 1 1 1.08 1.04L11.08 9l2.66 2.74a.75.75 0 1 1-1.08 1.04L10 10.06l-2.66 2.72a.75.75 0 1 1-1.08-1.04L8.92 9 6.28 6.26a.75.75 0 0 1 0-1.04Z" />
        </svg>
      </button>
    `;

    const closeBtn = div.querySelector("button");
    closeBtn?.addEventListener("click", () => dismissAlert(div));

    alertsEl.appendChild(div);

    window.setTimeout(() => {
      if (div.isConnected) {
        dismissAlert(div);
      }
    }, 5000);
  }

  function setEmptyDownloadsList() {
    if (!downloadListEl) return;
    downloadListEl.innerHTML = `<div class="text-sm opacity-70">${I18N.emptyList}</div>`;
    if (downloadAllBtn) downloadAllBtn.disabled = true;
  }

  function getMapTraceStatusTitle(status) {
    if (status === "completed") {
      return I18N.mapTraceStatusCompleted;
    }

    if (status === "processing") {
      return I18N.mapTraceStatusProcessing;
    }

    if (status === "failed") {
      return I18N.mapTraceStatusFailed;
    }

    return I18N.mapTraceStatusPending;
  }

  function renderMapTraceStatusMarkup(status) {
    if (status === "completed") {
      return `
        <span class="inline-flex items-center justify-center text-success">
          <svg xmlns="http://www.w3.org/2000/svg"
               viewBox="0 0 24 24"
               fill="none"
               stroke="currentColor"
               stroke-width="2.5"
               stroke-linecap="round"
               stroke-linejoin="round"
               class="w-5 h-5">
            <path d="M20 6 9 17l-5-5"></path>
          </svg>
        </span>
      `;
    }

    if (status === "processing") {
      return `<span class="loading loading-spinner loading-sm text-primary"></span>`;
    }

    if (status === "failed") {
      return `
        <span class="inline-flex items-center justify-center text-error">
          <svg xmlns="http://www.w3.org/2000/svg"
               viewBox="0 0 24 24"
               fill="none"
               stroke="currentColor"
               stroke-width="2"
               stroke-linecap="round"
               stroke-linejoin="round"
               class="w-5 h-5">
            <path d="M12 9v4"></path>
            <path d="M12 17h.01"></path>
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"></path>
          </svg>
        </span>
      `;
    }

    return `
      <span class="inline-flex items-center justify-center text-base-content/45">
        <svg xmlns="http://www.w3.org/2000/svg"
             viewBox="0 0 24 24"
             fill="none"
             stroke="currentColor"
             stroke-width="2"
             stroke-linecap="round"
             stroke-linejoin="round"
             class="w-5 h-5">
          <circle cx="12" cy="12" r="9"></circle>
          <path d="M8 12h8"></path>
        </svg>
      </span>
    `;
  }

  function syncMapTraceStatus(plan) {
    if (!mapTracesStatus) {
      return;
    }

    const status = plan?.trace_status || mapTracesPanel?.dataset.traceStatus || "pending";
    mapTracesStatus.innerHTML = renderMapTraceStatusMarkup(status);
    mapTracesStatus.title = getMapTraceStatusTitle(status);
    mapTracesStatus.dataset.traceStatus = status;
  }

  function clearMapTraceOverlays({ resetCheckbox = true } = {}) {
    traceOverlayGroup.clearLayers();

    if (resetCheckbox && mapTracesCheckbox) {
      mapTracesCheckbox.checked = false;
    }
  }

  function updateMapTraceControls(plan) {
    if (!mapTracesPanel || !mapTracesCheckbox) {
      return;
    }

    const canDraw = Boolean(plan?.can_draw_traces);

    if (!canDraw) {
      clearMapTraceOverlays({ resetCheckbox: true });
    }

    mapTracesCheckbox.disabled = !canDraw || drawingMapTraces;
    mapTracesCheckbox.setAttribute(
      "aria-disabled",
      canDraw && !drawingMapTraces ? "false" : "true"
    );

    if (!canDraw) {
      mapTracesCheckbox.title = I18N.mapTracesUnavailable;
    } else {
      mapTracesCheckbox.removeAttribute("title");
    }

    syncMapTraceStatus(plan);
  }

  async function fetchTileTraces(tile) {
    const cacheKey = String(tile.photo_id || tile.id || tile.traces_url || "");
    if (cacheKey && traceOverlayCache.has(cacheKey)) {
      return traceOverlayCache.get(cacheKey);
    }

    if (!tile.traces_url) {
      throw new Error(I18N.mapTracesError);
    }

    const tracesUrl = new URL(tile.traces_url, window.location.origin);
    tracesUrl.searchParams.set("_ts", Date.now().toString());

    const response = await fetch(tracesUrl.toString(), {
      headers: { Accept: "application/json" },
    });
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.error || I18N.mapTracesError);
    }

    const traces = {
      xs: Array.isArray(payload.xs) ? payload.xs : [],
      ys: Array.isArray(payload.ys) ? payload.ys : [],
    };

    if (cacheKey) {
      traceOverlayCache.set(cacheKey, traces);
    }

    return traces;
  }

  function buildTileTraceOverlay(tile, traces) {
    const width = Number(tile.width || currentPlan?.tile_width || 1024);
    const height = Number(tile.height || currentPlan?.tile_height || 640);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return null;
    }

    const xs = Array.isArray(traces.xs) ? traces.xs : [];
    const ys = Array.isArray(traces.ys) ? traces.ys : [];

    ctx.fillStyle = "#ff0000";
    for (let index = 0; index < xs.length; index += 1) {
      const x = Number(xs[index]);
      const y = Number(ys[index]);
      if (x >= 0 && x < width && y >= 0 && y < height) {
        ctx.fillRect(Math.round(x), Math.round(y), 1, 1);
      }
    }

    const bounds = L.latLngBounds(
      [tile.bounds.south, tile.bounds.west],
      [tile.bounds.north, tile.bounds.east]
    );

    return L.imageOverlay(canvas.toDataURL("image/png"), bounds, {
      opacity: 1,
      interactive: false,
    });
  }

  async function drawMapTraces({ silent = false } = {}) {
    if (!currentPlan?.can_draw_traces) {
      if (mapTracesCheckbox) {
        mapTracesCheckbox.checked = false;
      }
      updateMapTraceControls(currentPlan);
      if (!silent) {
        clearAlerts();
        addAlert("alert-warning", I18N.mapTracesUnavailable);
      }
      return false;
    }

    drawingMapTraces = true;
    updateMapTraceControls(currentPlan);

    if (!silent) {
      clearAlerts();
      addAlert("alert-info", I18N.mapTracesLoading);
    }

    try {
      traceOverlayGroup.clearLayers();

      for (const tile of currentPlan.tiles || []) {
        const traces = await fetchTileTraces(tile);
        const overlay = buildTileTraceOverlay(tile, traces);
        if (overlay) {
          overlay.addTo(traceOverlayGroup);
        }
      }

      if (!silent) {
        clearAlerts();
        addAlert("alert-success", I18N.mapTracesReady);
      }

      return true;
    } catch (error) {
      clearMapTraceOverlays({ resetCheckbox: true });
      clearAlerts();
      addAlert("alert-error", error.message || I18N.mapTracesError);
      return false;
    } finally {
      drawingMapTraces = false;
      updateMapTraceControls(currentPlan);
    }
  }

  function resetGridState() {
    gridGroup.clearLayers();
    traceOverlayGroup.clearLayers();
    traceOverlayCache.clear();
    previewGroup.clearLayers();
    if (activePreviewLayer) {
      layerControl.removeLayer(activePreviewLayer);
      activePreviewLayer = null;
    }
    currentPlan = null;
    setSourceSummary(I18N.sourcePending);
    setDownloadsSummary(I18N.downloadsPending);
    setEmptyDownloadsList();
    updateMapTraceControls(null);
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
      origin: selectedPoints[0]
        ? { lat: selectedPoints[0].lat, lng: selectedPoints[0].lng }
        : { lat: sw.lat, lng: sw.lng },
      destination: selectedPoints[1]
        ? { lat: selectedPoints[1].lat, lng: selectedPoints[1].lng }
        : { lat: ne.lat, lng: ne.lng },
      resolution: Number.parseFloat(resolutionSelect.value),
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
    traceOverlayGroup.clearLayers();

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

    updateMapTraceControls(plan);
  }

  function restoreInitialZone(zone) {
    if (!zone || !zone.bbox || !zone.plan) return;

    resetSelection();

    selectedPoints = [
      L.latLng(zone.origin.lat, zone.origin.lng),
      L.latLng(zone.destination.lat, zone.destination.lng),
    ];

    selectedPoints.forEach((point) => {
      L.marker(point).addTo(markersGroup);
    });

    selectionBounds = L.latLngBounds(
      [zone.bbox.south, zone.bbox.west],
      [zone.bbox.north, zone.bbox.east]
    );

    selectionRectangle = L.rectangle(selectionBounds, {
      color: "#f59e0b",
      weight: 2,
      fillOpacity: 0.15,
    }).addTo(selectionGroup);

    currentPlan = zone.plan;
    renderPreviewLayer(currentPlan);
    renderGrid(currentPlan);
    renderDownloadList(currentPlan);
    updateSelectionSummaryFromBounds(selectionBounds);

    if (resolutionSelect && currentPlan.requested_resolution) {
      resolutionSelect.value = String(currentPlan.requested_resolution);
    }

    setDownloadsSummary(
      `${formatTemplate(I18N.downloadsReady, {
        count: currentPlan.tile_count,
        resolution: Number(currentPlan.actual_resolution).toFixed(2),
        source: currentPlan.source.label,
      })} ${formatTemplate(I18N.tilesCount, {
        count: currentPlan.tile_count,
        width: currentPlan.tile_width,
        height: currentPlan.tile_height,
      })}`
    );

    map.fitBounds(selectionBounds.pad(0.15));
    clearAlerts();
    addAlert("alert-info", I18N.restoredZone);

    updateMapTraceControls(currentPlan);

    if (mapTracesCheckbox?.checked && currentPlan?.can_draw_traces) {
      drawMapTraces({ silent: true });
    }
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

      const contentType = response.headers.get("content-type") || "";
      let data = null;

      if (contentType.includes("application/json")) {
        data = await response.json();
      } else {
        const responseText = await response.text();
        clearAlerts();
        addAlert(
          "alert-error",
          `${I18N.gridGenerationError} (${response.status})`
        );
        console.error("Respuesta no JSON en /visor/grid-plan:", responseText);
        return;
      }

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
        `${formatTemplate(I18N.downloadsReady, {
          count: data.tile_count,
          resolution: data.actual_resolution.toFixed(2),
          source: data.source.label,
        })} ${formatTemplate(I18N.tilesCount, {
          count: data.tile_count,
          width: data.tile_width,
          height: data.tile_height,
        })}`
      );

      if (controlsModal?.open) {
        controlsModal.close();
      }

      if (data.parcel_id && URLS.collection) {
        addAlert(
          "alert-success",
          `${I18N.zoneRegistered} <a class="link font-semibold" href="${URLS.collection}">${I18N.openCollection}</a>`
        );
      }

      window.requestAnimationFrame(() => {
        scrollToDownloads();
      });

      (data.warnings || []).forEach((warning) => {
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

  openControlsBtn?.addEventListener("click", () => {
    controlsModal?.showModal();
  });

  generateGridBtn.addEventListener("click", generateGrid);
  resetSelectionBtn.addEventListener("click", resetSelection);
  downloadAllBtn.addEventListener("click", downloadZip);

  mapTracesCheckbox?.addEventListener("change", async () => {
    if (mapTracesCheckbox.checked) {
      await drawMapTraces();
      return;
    }

    clearMapTraceOverlays({ resetCheckbox: false });
  });

  setSelectionSummary(I18N.selectionPending);
  setSourceSummary(I18N.previewLatest);
  setDownloadsSummary(I18N.downloadsPending);
  setEmptyDownloadsList();
  updateMapTraceControls(null);

  if (initialZone) {
    restoreInitialZone(initialZone);
  }
});
