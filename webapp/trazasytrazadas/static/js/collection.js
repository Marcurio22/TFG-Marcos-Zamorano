/**
 * Lógica de interacción de la colección de imágenes.
 *
 * Gestiona la preview modal, el borrado con modal DaisyUI y el polling
 * ligero de estados para colección y galería.
 *
 * Autor: Marcos Zamorano Lasso
 * Versión: 0.1
 */

document.addEventListener("DOMContentLoaded", () => {
  const CFG = window.COLLECTION_APP || {};
  const I18N = Object.assign(
    {
      previewTitle: "Preview de la zona",
      previewError: "No se ha podido cargar la preview de la zona.",
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
      download: "Descargar",
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

  const perPageSelect = document.querySelector("[data-collection-per-page]");
  const galleryRoot = document.querySelector("[data-gallery-zone-root]");
  let pendingDeleteForm = null;

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
                  class="btn btn-sm btn-warning${retryDisabledClass}"${retryDisabledAttrs}>
            ${htmlEscape(I18N.recalculateTrace)}
          </button>
        </form>
      `);
    }

    if (options.downloadUrl) {
      parts.push(`
        <a href="${htmlEscape(options.downloadUrl)}" class="btn btn-sm btn-outline">${htmlEscape(I18N.download)}</a>
      `);
    }

    return parts.join("");
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