/**
 * Lógica de interacción de la colección de imágenes.
 *
 * Gestiona la preview modal, el borrado con modal DaisyUI, el visor ampliado
 * de teselas y el polling ligero de estados para colección y galería.
 *
 * Autor: Marcos Zamorano Lasso
 * Versión: 0.1
 */

document.addEventListener("DOMContentLoaded", () => {
  const CFG = window.COLLECTION_APP || {};
  const I18N = Object.assign(
    {
      previewTitle: "Vista previa de la zona",
      previewError: "No se ha podido cargar la vista previa de la zona.",
      progressText: "{completed}/{total} teselas completadas",
      zoneCompleted: "Trazas completadas",
      zoneProcessing: "Procesando",
      zonePending: "En espera",
      zoneFailed: "Error",
      photoCompleted: "Trazas calculadas",
      photoProcessing: "Calculando trazas",
      photoPending: "Trazas no calculadas",
      photoFailed: "Error de cálculo",
      photoStale: "Procesamiento atascado",
      retryTrace: "Reintentar",
      recalculateTrace: "Recalcular trazas",
      drawTrace: "Dibujar trazas",
      download: "Descargar",
      viewerImagePreview: "Vista ampliada de la tesela seleccionada.",
      viewerDrawn: "Trazas dibujadas",
      viewerNotDrawn: "Sin dibujar",
      viewerDrawing: "Dibujando...",
      viewerDrawUnavailable: "Todavía no hay trazas calculadas para esta tesela.",
      viewerDrawError: "No se han podido dibujar las trazas sobre la imagen.",
      recalculatePhotoTitle: "Vuelve a ejecutar el cálculo de trazas para esta tesela.",
      recalculatePhotoDisabledTitle: "Disponible cuando la tesela esté pendiente el tiempo suficiente o haya fallado.",
      downloadPhotoTitle: "Descarga la imagen de esta tesela.",
    },
    CFG.i18n || {}
  );

  const POLL_INTERVAL_MS = Number(CFG.pollIntervalMs || 5000);

  const previewModal = document.getElementById("zone-preview-modal");
  const previewTitle = document.getElementById("zone-preview-title");
  const loadingEl = document.getElementById("zone-preview-loading");
  const errorEl = document.getElementById("zone-preview-error");
  const imageEl = document.getElementById("zone-preview-image");

  const deleteModal = document.getElementById("zone-delete-modal");
  const deleteZoneId = document.getElementById("delete-zone-id");
  const deleteZoneOrigin = document.getElementById("delete-zone-origin");
  const deleteZoneDestination = document.getElementById("delete-zone-destination");
  const confirmDeleteButton = document.getElementById("confirm-delete-button");
  const renameModal = document.getElementById("zone-rename-modal");
  const renameForm = document.getElementById("zone-rename-form");
  const renameInput = document.getElementById("rename-zone-name-input");
  const renameRedirect = document.getElementById("rename-zone-redirect-to");
  const renameCurrentDisplay = document.getElementById("rename-zone-current-display");

  const photoViewerModal = document.getElementById("photo-viewer-modal");
  const photoViewerTitle = document.getElementById("photo-viewer-title");
  const photoViewerSubtitle = document.getElementById("photo-viewer-subtitle");
  const photoViewerImage = document.getElementById("photo-viewer-image");
  const photoViewerCanvas = document.getElementById("photo-viewer-canvas");
  const photoViewerLoading = document.getElementById("photo-viewer-loading");
  const photoViewerError = document.getElementById("photo-viewer-error");
  const photoViewerFilename = document.getElementById("photo-viewer-filename");
  const photoViewerCenter = document.getElementById("photo-viewer-center");
  const photoViewerDimensions = document.getElementById("photo-viewer-dimensions");
  const photoViewerRetryForm = document.getElementById("photo-viewer-retry-form");
  const photoViewerRetryButton = document.getElementById("photo-viewer-retry-button");
  const zoneRetryAllButton = document.querySelector("[data-zone-retry-all-button]");
  const photoViewerRetryRedirect = document.getElementById("photo-viewer-retry-redirect");
  const photoViewerDrawToggle = document.getElementById("photo-viewer-draw-toggle");
  const photoViewerDownloadLink = document.getElementById("photo-viewer-download-link");
  const photoViewerTraceStatus = document.getElementById("photo-viewer-trace-status");

  const perPageSelect = document.querySelector("[data-collection-per-page]");
  const galleryRoot = document.querySelector("[data-gallery-zone-root]");
  let pendingDeleteForm = null;
  let currentViewerPhotoId = null;
  let currentViewerTraces = null;

  function htmlEscape(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatTemplate(template, values) {
    return Object.entries(values).reduce((result, [key, value]) => {
      return result.replaceAll(`{${key}}`, String(value));
    }, template);
  }

  function isDialogOpen(dialogEl) {
    return Boolean(dialogEl && dialogEl.open);
  }

  function renderZoneStateMarkup(status) {
    if (status === "completed") {
      return `
        <span class="inline-flex items-center justify-center text-success" title="${I18N.zoneCompleted}">
          <svg xmlns="http://www.w3.org/2000/svg"
               viewBox="0 0 24 24"
               fill="none"
               stroke="currentColor"
               stroke-width="2.5"
               stroke-linecap="round"
               stroke-linejoin="round"
               class="w-6 h-6">
            <path d="M20 6 9 17l-5-5"></path>
          </svg>
        </span>
      `;
    }

    if (status === "processing") {
      return `<span class="loading loading-spinner loading-md text-primary" title="${I18N.zoneProcessing}"></span>`;
    }

    if (status === "failed") {
      return `<span class="badge badge-error badge-outline">${I18N.zoneFailed}</span>`;
    }

    return `<span class="badge badge-neutral badge-outline">${I18N.zonePending}</span>`;
  }

  function renderZoneBadgeMarkup(status) {
    if (status === "completed") {
      return `<span class="badge badge-success badge-outline">${I18N.zoneCompleted}</span>`;
    }

    if (status === "processing") {
      return `<span class="badge badge-info badge-outline">${I18N.zoneProcessing}</span>`;
    }

    if (status === "failed") {
      return `<span class="badge badge-error badge-outline">${I18N.zoneFailed}</span>`;
    }

    return `<span class="badge badge-neutral badge-outline">${I18N.zonePending}</span>`;
  }

  function updateZoneRetryAllButton(payload) {
    if (!zoneRetryAllButton) {
      return;
    }

    const total = Number(payload.tile_count || 0);
    const completed = Number(payload.completed_tiles || 0);
    const allCompleted = total > 0 && completed === total;
    const canRetryAll = Boolean(payload.can_retry_all);

    zoneRetryAllButton.disabled = !canRetryAll;
    zoneRetryAllButton.classList.toggle("btn-disabled", !canRetryAll);
    zoneRetryAllButton.setAttribute(
      "aria-disabled",
      canRetryAll ? "false" : "true"
    );

    if (canRetryAll) {
      zoneRetryAllButton.title = I18N.retryZoneReady || "";
    } else if (allCompleted) {
      zoneRetryAllButton.title = I18N.retryZoneDisabledCompleted || "";
    } else {
      zoneRetryAllButton.title = I18N.retryZoneDisabledWait || "";
    }
  }

  function renderPhotoStateMarkup(status, isStale) {
    if (isStale) {
      return `
        <span class="inline-flex items-center justify-center text-warning" title="${I18N.photoStale}">
          <svg xmlns="http://www.w3.org/2000/svg"
               viewBox="0 0 24 24"
               fill="none"
               stroke="currentColor"
               stroke-width="2"
               stroke-linecap="round"
               stroke-linejoin="round"
               class="w-6 h-6">
            <path d="M12 9v4"></path>
            <path d="M12 17h.01"></path>
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"></path>
          </svg>
        </span>
      `;
    }

    if (status === "completed") {
      return `
        <span class="inline-flex items-center justify-center text-success" title="${I18N.photoCompleted}">
          <svg xmlns="http://www.w3.org/2000/svg"
               viewBox="0 0 24 24"
               fill="none"
               stroke="currentColor"
               stroke-width="2.5"
               stroke-linecap="round"
               stroke-linejoin="round"
               class="w-6 h-6">
            <path d="M20 6 9 17l-5-5"></path>
          </svg>
        </span>
      `;
    }

    if (status === "processing") {
      return `<span class="loading loading-spinner loading-md text-primary" title="${I18N.photoProcessing}"></span>`;
    }

    if (status === "failed") {
      return `
        <span class="inline-flex items-center justify-center text-error" title="${I18N.photoFailed}">
          <svg xmlns="http://www.w3.org/2000/svg"
               viewBox="0 0 24 24"
               fill="none"
               stroke="currentColor"
               stroke-width="2"
               stroke-linecap="round"
               stroke-linejoin="round"
               class="w-6 h-6">
            <path d="M12 9v4"></path>
            <path d="M12 17h.01"></path>
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"></path>
          </svg>
        </span>
      `;
    }

    return `
      <span class="inline-flex items-center justify-center text-base-content/45" title="${I18N.photoPending}">
        <svg xmlns="http://www.w3.org/2000/svg"
             viewBox="0 0 24 24"
             fill="none"
             stroke="currentColor"
             stroke-width="2"
             stroke-linecap="round"
             stroke-linejoin="round"
             class="w-6 h-6">
          <circle cx="12" cy="12" r="9"></circle>
          <path d="M8 12h8"></path>
        </svg>
      </span>
    `;
  }

  function renderPhotoActionsMarkup(options) {
    const parts = [];
    const redirectTo = window.location.pathname + window.location.search;
    const retryDisabledAttrs = options.canRetry ? "" : ' disabled aria-disabled="true"';
    const retryDisabledClass = options.canRetry ? "" : " btn-disabled";

    if (options.retryUrl) {
      parts.push(`
        <form method="post" action="${htmlEscape(options.retryUrl)}" class="inline-flex">
          <input type="hidden" name="redirect_to" value="${htmlEscape(redirectTo)}">
          <button type="submit"
                  class="btn btn-sm btn-warning${retryDisabledClass}"
                  title="${htmlEscape(options.canRetry ? I18N.recalculatePhotoTitle : I18N.recalculatePhotoDisabledTitle)}"${retryDisabledAttrs}>
            ${htmlEscape(I18N.recalculateTrace)}
          </button>
        </form>
      `);
    }

    if (options.downloadUrl) {
      parts.push(`
        <a href="${htmlEscape(options.downloadUrl)}"
          class="btn btn-sm btn-outline"
          title="${htmlEscape(I18N.downloadPhotoTitle)}">${htmlEscape(I18N.download)}</a>
      `);
    }

    return parts.join("");
  }

  function getPhotoVisualTraceStatus(photo) {
    if (!photo) {
      return "pending";
    }

    if (photo.status === "failed") {
      return "failed";
    }

    return photo.traceStatus || "pending";
  }

  function getPhotoVisualTraceTitle(status) {
    if (status === "completed") {
      return I18N.photoCompleted;
    }

    if (status === "processing") {
      return I18N.photoProcessing;
    }

    if (status === "failed") {
      return I18N.photoFailed;
    }

    return I18N.photoPending;
  }

  function syncPhotoViewerTraceStatus() {
    if (!photoViewerTraceStatus) {
      return;
    }

    const card = getPhotoCard(currentViewerPhotoId);
    const photo = getPhotoDataFromCard(card);
    const visualStatus = getPhotoVisualTraceStatus(photo);

    photoViewerTraceStatus.innerHTML = renderPhotoStateMarkup(visualStatus, false);
    photoViewerTraceStatus.title = getPhotoVisualTraceTitle(visualStatus);
    photoViewerTraceStatus.dataset.photoState = visualStatus;
  }

  function resetPhotoViewerDrawToggle() {
    if (!photoViewerDrawToggle) {
      return;
    }

    photoViewerDrawToggle.checked = false;
    photoViewerDrawToggle.disabled = true;
    photoViewerDrawToggle.setAttribute("aria-disabled", "true");
  }

  function resetPreviewModal() {
    if (!loadingEl || !errorEl || !imageEl) return;
    loadingEl.classList.remove("hidden");
    errorEl.classList.add("hidden");
    errorEl.textContent = "";
    imageEl.classList.add("hidden");
    imageEl.removeAttribute("src");
  }

  function showPreviewError(message) {
    if (!loadingEl || !errorEl || !imageEl) return;
    loadingEl.classList.add("hidden");
    imageEl.classList.add("hidden");
    errorEl.textContent = message;
    errorEl.classList.remove("hidden");
  }

  function getPhotoCard(photoId) {
    if (!photoId) {
      return null;
    }

    return Array.from(document.querySelectorAll("[data-gallery-photo-card]")).find(
      (card) => String(card.dataset.photoId || "") === String(photoId)
    ) || null;
  }

  function getPhotoDataFromCard(card) {
    if (!card) {
      return null;
    }

    return {
      photoId: String(card.dataset.photoId || ""),
      title: card.dataset.photoTitle || "",
      imageUrl: card.dataset.photoImageUrl || "",
      tracesUrl: card.dataset.photoTracesUrl || "",
      downloadUrl: card.dataset.photoDownloadUrl || "",
      retryUrl: card.dataset.photoRetryUrl || "",
      filename: card.dataset.photoFilename || "",
      centerLat: card.dataset.photoCenterLat || "",
      centerLng: card.dataset.photoCenterLng || "",
      width: Number(card.dataset.photoWidth || 0),
      height: Number(card.dataset.photoHeight || 0),
      status: card.dataset.photoState || "pending",
      traceStatus: card.dataset.photoTraceStatus || "pending",
      canRetry: card.dataset.photoCanRetry === "1",
    };
  }

  function clearPhotoViewerError() {
    if (!photoViewerError) {
      return;
    }
    photoViewerError.textContent = "";
    photoViewerError.classList.add("hidden");
  }

  function showPhotoViewerError(message) {
    if (!photoViewerError) {
      return;
    }
    photoViewerError.textContent = message;
    photoViewerError.classList.remove("hidden");
  }

  function clearPhotoViewerOverlay() {
    currentViewerTraces = null;
    if (!photoViewerCanvas) {
      return;
    }
    const ctx = photoViewerCanvas.getContext("2d");
    if (ctx) {
      ctx.clearRect(0, 0, photoViewerCanvas.width, photoViewerCanvas.height);
    }
    photoViewerCanvas.classList.add("hidden");
    syncPhotoViewerTraceStatus();
  }

  function resizePhotoViewerCanvas() {
    if (!photoViewerImage || !photoViewerCanvas) {
      return;
    }
    if (!photoViewerImage.complete || photoViewerImage.naturalWidth <= 0) {
      return;
    }

    const width = photoViewerImage.clientWidth;
    const height = photoViewerImage.clientHeight;
    if (width <= 0 || height <= 0) {
      return;
    }

    photoViewerCanvas.width = width;
    photoViewerCanvas.height = height;
    photoViewerCanvas.style.width = `${width}px`;
    photoViewerCanvas.style.height = `${height}px`;
  }

  function drawCurrentViewerTraces() {
    if (!photoViewerImage || !photoViewerCanvas || !currentViewerTraces) {
      return;
    }
    if (!photoViewerImage.complete || photoViewerImage.naturalWidth <= 0) {
      return;
    }

    resizePhotoViewerCanvas();

    const ctx = photoViewerCanvas.getContext("2d");
    if (!ctx) {
      return;
    }

    ctx.clearRect(0, 0, photoViewerCanvas.width, photoViewerCanvas.height);

    const scaleX = photoViewerCanvas.width / photoViewerImage.naturalWidth;
    const scaleY = photoViewerCanvas.height / photoViewerImage.naturalHeight;
    const xs = Array.isArray(currentViewerTraces.xs) ? currentViewerTraces.xs : [];
    const ys = Array.isArray(currentViewerTraces.ys) ? currentViewerTraces.ys : [];

    ctx.fillStyle = "#ff0000";
    for (let index = 0; index < xs.length; index += 1) {
      ctx.fillRect(xs[index] * scaleX, ys[index] * scaleY, 1, 1);
    }

    photoViewerCanvas.classList.remove("hidden");
    syncPhotoViewerTraceStatus();
  }

  function updatePhotoViewerControls(photo) {
    if (!photo) {
      return;
    }

    if (photoViewerRetryForm) {
      photoViewerRetryForm.setAttribute("action", photo.retryUrl || "");
    }

    if (photoViewerRetryRedirect) {
      photoViewerRetryRedirect.value = window.location.pathname + window.location.search;
    }

    if (photoViewerRetryButton) {
      photoViewerRetryButton.disabled = !photo.canRetry;
      photoViewerRetryButton.classList.toggle("btn-disabled", !photo.canRetry);
    }

    if (photoViewerDrawToggle) {
      const canDraw = photo.traceStatus === "completed";

      if (!canDraw && photoViewerDrawToggle.checked) {
        photoViewerDrawToggle.checked = false;
        clearPhotoViewerOverlay();
      }

      photoViewerDrawToggle.disabled = !canDraw;
      photoViewerDrawToggle.setAttribute(
        "aria-disabled",
        canDraw ? "false" : "true"
      );
    }

    if (photoViewerDownloadLink) {
      photoViewerDownloadLink.setAttribute("href", photo.downloadUrl || "#");
    }
  }

  function populatePhotoViewer(photo) {
    if (!photoViewerModal || !photo) {
      return;
    }

    currentViewerPhotoId = photo.photoId;
    clearPhotoViewerError();
    clearPhotoViewerOverlay();

    if (photoViewerDrawToggle) {
      photoViewerDrawToggle.checked = false;
    }
    if (photoViewerTitle) {
      photoViewerTitle.textContent = photo.title;
    }
    if (photoViewerSubtitle) {
      photoViewerSubtitle.textContent = I18N.viewerImagePreview;
    }
    if (photoViewerFilename) {
      photoViewerFilename.textContent = photo.filename;
    }
    if (photoViewerCenter) {
      photoViewerCenter.textContent = `${photo.centerLat}, ${photo.centerLng}`;
    }
    if (photoViewerDimensions) {
      photoViewerDimensions.textContent = `${photo.width} × ${photo.height}px`;
    }

    updatePhotoViewerControls(photo);
    syncPhotoViewerTraceStatus();

    if (photoViewerLoading) {
      photoViewerLoading.classList.remove("hidden");
      photoViewerLoading.classList.add("flex");
    }

    if (photoViewerImage) {
      photoViewerImage.onload = () => {
        if (photoViewerLoading) {
          photoViewerLoading.classList.add("hidden");
          photoViewerLoading.classList.remove("flex");
        }
        resizePhotoViewerCanvas();
        if (currentViewerTraces) {
          drawCurrentViewerTraces();
        }
      };

      photoViewerImage.onerror = () => {
        if (photoViewerLoading) {
          photoViewerLoading.classList.add("hidden");
          photoViewerLoading.classList.remove("flex");
        }
        showPhotoViewerError(I18N.previewError);
      };

      const imageUrl = new URL(photo.imageUrl, window.location.origin);
      imageUrl.searchParams.set("_ts", Date.now().toString());
      photoViewerImage.src = imageUrl.toString();
      photoViewerImage.alt = photo.title;
    }
  }

  async function drawViewerTraces() {
    const card = getPhotoCard(currentViewerPhotoId);
    const photo = getPhotoDataFromCard(card);
    if (!photo) {
      return false;
    }

    if (photo.traceStatus !== "completed") {
      showPhotoViewerError(I18N.viewerDrawUnavailable);
      return false;
    }

    clearPhotoViewerError();
    syncPhotoViewerTraceStatus();

    try {
      const tracesUrl = new URL(photo.tracesUrl, window.location.origin);
      tracesUrl.searchParams.set("_ts", Date.now().toString());
      const response = await fetch(tracesUrl.toString(), {
        headers: { Accept: "application/json" },
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || I18N.viewerDrawError);
      }

      currentViewerTraces = {
        xs: Array.isArray(payload.xs) ? payload.xs : [],
        ys: Array.isArray(payload.ys) ? payload.ys : [],
      };
      drawCurrentViewerTraces();
      return true;
    } catch (error) {
      clearPhotoViewerOverlay();
      showPhotoViewerError(error.message || I18N.viewerDrawError);
      return false;
    }
  }

  document.querySelectorAll("[data-action='open-zone-preview']").forEach((button) => {
    button.addEventListener("click", () => {
      const previewUrl = button.dataset.previewUrl;
      const title = button.dataset.previewTitle || I18N.previewTitle;

      if (!previewModal || !imageEl) {
        window.open(previewUrl, "_blank", "noopener");
        return;
      }

      resetPreviewModal();
      if (previewTitle) previewTitle.textContent = title;
      previewModal.showModal();

      const url = new URL(previewUrl, window.location.origin);
      url.searchParams.set("_ts", Date.now().toString());

      imageEl.onload = () => {
        if (loadingEl) loadingEl.classList.add("hidden");
        if (errorEl) errorEl.classList.add("hidden");
        imageEl.classList.remove("hidden");
      };

      imageEl.onerror = () => {
        showPreviewError(I18N.previewError);
      };

      imageEl.src = url.toString();
    });
  });

  document.querySelectorAll("[data-action='open-photo-viewer']").forEach((button) => {
    button.addEventListener("click", () => {
      const card = button.closest("[data-gallery-photo-card]");
      const photo = getPhotoDataFromCard(card);
      if (!photo) {
        return;
      }

      if (!photoViewerModal || !photoViewerImage) {
        window.open(photo.imageUrl, "_blank", "noopener");
        return;
      }

      populatePhotoViewer(photo);
      if (!isDialogOpen(photoViewerModal)) {
        photoViewerModal.showModal();
      }
    });
  });

  if (photoViewerDrawToggle) {
    photoViewerDrawToggle.addEventListener("change", async () => {
      if (photoViewerDrawToggle.disabled) {
        photoViewerDrawToggle.checked = false;
        return;
      }

      if (!photoViewerDrawToggle.checked) {
        clearPhotoViewerError();
        clearPhotoViewerOverlay();
        return;
      }

      const drawn = await drawViewerTraces();
      if (!drawn) {
        photoViewerDrawToggle.checked = false;
      }
    });
  }

  if (photoViewerModal) {
    photoViewerModal.addEventListener("close", () => {
      currentViewerPhotoId = null;
      clearPhotoViewerError();
      clearPhotoViewerOverlay();
      resetPhotoViewerDrawToggle();
      if (photoViewerImage) {
        photoViewerImage.removeAttribute("src");
        photoViewerImage.alt = "";
      }
      if (photoViewerLoading) {
        photoViewerLoading.classList.add("hidden");
        photoViewerLoading.classList.remove("flex");
      }
    });
  }

  if (photoViewerImage && photoViewerCanvas) {
    window.addEventListener("resize", () => {
      if (isDialogOpen(photoViewerModal)) {
        resizePhotoViewerCanvas();
        if (currentViewerTraces) {
          drawCurrentViewerTraces();
        }
      }
    });
  }

  document.querySelectorAll("[data-action='open-delete-modal']").forEach((button) => {
    button.addEventListener("click", () => {
      pendingDeleteForm = button.closest("form[data-delete-form]");

      if (deleteZoneId) deleteZoneId.textContent = `#${button.dataset.zoneId || "—"}`;
      if (deleteZoneOrigin) deleteZoneOrigin.textContent = button.dataset.zoneOrigin || "—";
      if (deleteZoneDestination) {
        deleteZoneDestination.textContent = button.dataset.zoneDestination || "—";
      }

      if (deleteModal) {
        deleteModal.showModal();
      }
    });
  });

  if (confirmDeleteButton) {
    confirmDeleteButton.addEventListener("click", () => {
      if (deleteModal) {
        deleteModal.close();
      }
      if (pendingDeleteForm) {
        pendingDeleteForm.submit();
      }
    });
  }

  document.querySelectorAll("[data-action='open-zone-rename']").forEach((button) => {
    button.addEventListener("click", () => {
      if (!renameModal || !renameForm || !renameInput) {
        return;
      }

      renameForm.setAttribute("action", button.dataset.renameUrl || "");
      renameInput.value = button.dataset.zoneName || "";

      if (renameRedirect) {
        renameRedirect.value =
          button.dataset.redirectTo || (window.location.pathname + window.location.search);
      }

      if (renameCurrentDisplay) {
        renameCurrentDisplay.textContent = button.dataset.zoneDisplayName || "";
      }

      renameModal.showModal();
      window.setTimeout(() => {
        renameInput.focus();
        renameInput.select();
      }, 50);
    });
  });

  if (perPageSelect) {
    perPageSelect.addEventListener("change", () => {
      const form = perPageSelect.closest("form");
      if (form) form.submit();
    });
  }

  async function refreshCollectionStatuses() {
    const statusUrl = CFG.urls && CFG.urls.statusCollection;
    const rows = Array.from(document.querySelectorAll("[data-zone-row]"));
    if (!statusUrl || rows.length === 0) {
      return;
    }

    const ids = rows
      .map((row) => row.dataset.zoneId)
      .filter(Boolean)
      .join(",");

    if (!ids) {
      return;
    }

    const url = new URL(statusUrl, window.location.origin);
    url.searchParams.set("ids", ids);
    url.searchParams.set("_ts", Date.now().toString());

    const response = await fetch(url.toString(), {
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      return;
    }

    const payload = await response.json();
    const zones = Array.isArray(payload.zones) ? payload.zones : [];
    const byId = new Map(zones.map((zone) => [String(zone.parcela_id), zone]));

    rows.forEach((row) => {
      const zone = byId.get(row.dataset.zoneId);
      if (!zone) {
        return;
      }

      const stateEl = row.querySelector("[data-zone-state]");
      const progressEl = row.querySelector("[data-zone-progress]");

      if (stateEl) {
        stateEl.innerHTML = renderZoneStateMarkup(zone.estado || zone.status);
        stateEl.dataset.zoneStatus = zone.estado || zone.status;
      }

      if (progressEl) {
        progressEl.textContent = formatTemplate(I18N.progressText, {
          completed: zone.completed_tiles || 0,
          total: zone.tile_count || 0,
        });
      }
    });
  }

  async function refreshGalleryStatus() {
    if (!galleryRoot) {
      return;
    }

    const statusUrl = galleryRoot.dataset.zoneStatusUrl;
    if (!statusUrl) {
      return;
    }

    const url = new URL(statusUrl, window.location.origin);
    url.searchParams.set("_ts", Date.now().toString());

    const response = await fetch(url.toString(), {
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      return;
    }

    const payload = await response.json();
    const badgeEl = document.querySelector("[data-zone-status-badge]");
    const progressSummaryEl = document.querySelector("[data-zone-progress-summary]");

    if (badgeEl) {
      badgeEl.innerHTML = renderZoneBadgeMarkup(payload.estado || payload.status);
    }

    updateZoneRetryAllButton(payload);

    if (progressSummaryEl) {
      progressSummaryEl.textContent = formatTemplate(I18N.progressText, {
        completed: payload.completed_tiles || 0,
        total: payload.tile_count || 0,
      });
    }

    const photos = Array.isArray(payload.photos) ? payload.photos : [];
    const byId = new Map(photos.map((photo) => [String(photo.foto_id), photo]));

    document.querySelectorAll("[data-photo-status]").forEach((container) => {
      const photo = byId.get(container.dataset.photoId);
      if (!photo) {
        return;
      }

      const isStale = Boolean(photo.is_stale);
      container.innerHTML = renderPhotoStateMarkup(photo.estado, isStale);
      container.dataset.photoState = photo.estado;

      if (isStale) {
        container.title = I18N.photoStale;
      } else if (photo.estado === "completed") {
        container.title = I18N.photoCompleted;
      } else if (photo.estado === "processing") {
        container.title = I18N.photoProcessing;
      } else if (photo.estado === "failed") {
        container.title = I18N.photoFailed;
      } else {
        container.title = I18N.photoPending;
      }
    });

    document.querySelectorAll("[data-photo-actions]").forEach((container) => {
      const photo = byId.get(container.dataset.photoId);
      if (!photo) {
        return;
      }

      container.innerHTML = renderPhotoActionsMarkup({
        status: photo.estado,
        canRetry: Boolean(photo.can_retry),
        retryUrl: container.dataset.photoRetryUrl,
        downloadUrl: container.dataset.photoDownloadUrl,
      });
    });

    document.querySelectorAll("[data-gallery-photo-card]").forEach((card) => {
      const photo = byId.get(card.dataset.photoId);
      if (!photo) {
        return;
      }

      card.dataset.photoState = photo.estado || "pending";
      card.dataset.photoTraceStatus = photo.trace_status || "pending";
      card.dataset.photoCanRetry = photo.can_retry ? "1" : "0";

      if (currentViewerPhotoId && currentViewerPhotoId === String(photo.foto_id)) {
        updatePhotoViewerControls(getPhotoDataFromCard(card));
        syncPhotoViewerTraceStatus();
      }
    });
  }

  async function runPollingTick() {
    try {
      await refreshCollectionStatuses();
      await refreshGalleryStatus();
    } catch (_error) {
      // Polling silencioso: no interrumpe la UI si falla una consulta puntual.
    }
  }

  if (document.querySelector("[data-zone-row]") || galleryRoot) {
    window.setInterval(runPollingTick, Math.max(1000, POLL_INTERVAL_MS));
  }
});
