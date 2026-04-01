/**
 * Lógica de interacción de la colección de imágenes.
 *
 * Gestiona la preview modal de cada zona, el auto-submit del selector de
 * tamaño de página y la confirmación visual previa al borrado permanente.
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
    },
    CFG.i18n || {}
  );

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

  const perPageSelect = document.querySelector("[data-collection-per-page]");
  let pendingDeleteForm = null;

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

  if (perPageSelect) {
    perPageSelect.addEventListener("change", () => {
      const form = perPageSelect.closest("form");
      if (form) form.submit();
    });
  }
});