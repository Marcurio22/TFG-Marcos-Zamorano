/**
 * Lógica de interacción de la colección de imágenes.
 *
 * Gestiona la preview modal de cada zona, el auto-submit del selector de
 * tamaño de página y la confirmación previa al borrado permanente.
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
      deleteConfirm: "¿Eliminar esta zona de forma permanente?",
    },
    CFG.i18n || {}
  );

  const modal = document.getElementById("zone-preview-modal");
  const modalTitle = document.getElementById("zone-preview-title");
  const loadingEl = document.getElementById("zone-preview-loading");
  const errorEl = document.getElementById("zone-preview-error");
  const imageEl = document.getElementById("zone-preview-image");
  const perPageSelect = document.querySelector("[data-collection-per-page]");

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
      const previewTitle = button.dataset.previewTitle || I18N.previewTitle;

      if (!modal || !imageEl) {
        window.open(previewUrl, "_blank", "noopener");
        return;
      }

      resetPreviewModal();
      if (modalTitle) modalTitle.textContent = previewTitle;
      modal.showModal();

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

  document.querySelectorAll("[data-action='confirm-delete']").forEach((button) => {
    button.addEventListener("click", (event) => {
      const message = button.dataset.confirmMessage || I18N.deleteConfirm;
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  });

  if (perPageSelect) {
    perPageSelect.addEventListener("change", () => {
      const form = perPageSelect.closest("form");
      if (form) form.submit();
    });
  }
});