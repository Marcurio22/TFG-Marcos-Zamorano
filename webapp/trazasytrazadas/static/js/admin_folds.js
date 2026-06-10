/**
 * Lógica de administración de modelos.
 *
 * Controla la subida de modelos, el progreso de carga, la cancelación de la
 * transferencia y los modales de acciones administrativas.
 *
 * Autor: Marcos Zamorano Lasso
 * Versión: 1.0
 */
/* global window, document, FormData, XMLHttpRequest */
(() => {
  "use strict";

  const config = window.ADMIN_FOLDS_APP || {};
  const messages = config.messages || {};
  let refreshTimer = null;
  let uploadInProgress = false;
  let activeUploadXhr = null;

  // Obtiene un mensaje traducido con valor por defecto.
  function message(key, fallback) {
    return messages[key] || fallback;
  }

  // Inicia la recarga periódica cuando no hay acciones abiertas.
  function startRefreshLoop() {
    if (refreshTimer) {
      return;
    }

    refreshTimer = window.setInterval(() => {
      const openDialog = document.querySelector("dialog[open]");
      if (!openDialog && !uploadInProgress) {
        window.location.reload();
      }
    }, 5000);
  }

  // Cierra un diálogo si está abierto.
  function closeDialog(dialog) {
    if (dialog?.open && typeof dialog.close === "function") {
      dialog.close();
    }
  }

  // Oculta y elimina un aviso de la pantalla.
  function dismissToast(alertEl) {
    if (!alertEl) {
      return;
    }

    alertEl.style.transition = "opacity 250ms ease";
    alertEl.style.opacity = "0";
    window.setTimeout(() => alertEl.remove(), 260);
  }

  // Construye el icono de cierre usado en los avisos.
  function makeCloseIcon() {
    const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.setAttribute("viewBox", "0 0 20 20");
    icon.setAttribute("fill", "currentColor");
    icon.classList.add("w-4", "h-4");

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute(
      "d",
      "M6.28 5.22a.75.75 0 0 1 1.06 0L10 7.94l2.66-2.72"
        + "a.75.75 0 1 1 1.08 1.04L11.08 9l2.66 2.74a.75.75"
        + " 0 1 1-1.08 1.04L10 10.06l-2.66 2.72a.75.75 0 1"
        + " 1-1.08-1.04L8.92 9 6.28 6.26a.75.75 0 0 1 0-1.04Z"
    );

    icon.appendChild(path);
    return icon;
  }

  // Muestra el aviso de cancelación de subida.
  function showCancellationToast() {
    const toastContainer = document.querySelector(
      "[data-upload-toast-container]"
    );
    if (!toastContainer) {
      return;
    }

    toastContainer.innerHTML = "";

    const alertEl = document.createElement("div");
    alertEl.className = "alert alert-info shadow-lg pointer-events-auto";

    const text = document.createElement("span");
    text.className = "text-sm sm:text-base";
    text.textContent = message(
      "cancelledToastMessage",
      "La subida se ha cancelado correctamente. "
        + "No se ha guardado ningún modelo."
    );

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "btn btn-sm btn-ghost ml-auto";
    closeButton.setAttribute("aria-label", message("close", "Cerrar"));
    closeButton.appendChild(makeCloseIcon());
    closeButton.addEventListener("click", () => dismissToast(alertEl));

    alertEl.append(text, closeButton);
    toastContainer.appendChild(alertEl);

    window.setTimeout(() => {
      if (alertEl.isConnected) {
        dismissToast(alertEl);
      }
    }, 5000);
  }

  // Actualiza el bloque de progreso de subida.
  function showProgress(text) {
    const progressBox = document.querySelector("[data-model-upload-progress]");
    const progressText = document.querySelector("[data-upload-progress-text]");
    if (!progressBox || !progressText) {
      return;
    }

    progressBox.classList.remove("hidden");
    progressText.textContent = text;
  }

  // Muestra u oculta el botón de cancelar subida.
  function setCancelButtonVisible(visible) {
    const cancelButton = document.querySelector("[data-upload-cancel-button]");
    if (!cancelButton) {
      return;
    }

    cancelButton.classList.toggle("hidden", !visible);
    cancelButton.disabled = !visible;
  }

  // Muestra u oculta el indicador de carga.
  function setSpinnerVisible(visible) {
    const spinner = document.querySelector("[data-upload-progress-spinner]");
    if (!spinner) {
      return;
    }

    spinner.classList.toggle("hidden", !visible);
  }

  // Reinicia la interfaz de progreso antes de una subida.
  function resetProgressUi() {
    const progressBox = document.querySelector("[data-model-upload-progress]");
    const progressBar = document.querySelector("[data-upload-progress-bar]");

    if (progressBox) {
      progressBox.classList.remove("hidden");
    }

    if (progressBar) {
      progressBar.value = 0;
    }

    setSpinnerVisible(true);
    setCancelButtonVisible(true);
  }

  // Oculta el bloque de progreso de subida.
  function hideProgressUi() {
    const progressBox = document.querySelector("[data-model-upload-progress]");
    const progressBar = document.querySelector("[data-upload-progress-bar]");

    if (progressBar) {
      progressBar.value = 0;
    }

    if (progressBox) {
      progressBox.classList.add("hidden");
    }
  }

  // Actualiza el porcentaje visible de la subida.
  function updateProgress(percent) {
    const progressBar = document.querySelector("[data-upload-progress-bar]");
    const boundedPercent = Math.max(0, Math.min(100, percent));
    const prefix = message("uploadingPrefix", "Subiendo");
    const suffix = message("uploadingSuffix", "del archivo.");

    if (progressBar) {
      progressBar.value = boundedPercent;
    }

    showProgress(`${prefix} ${boundedPercent}% ${suffix}`);
  }

  // Marca la subida como finalizada en la interfaz.
  function finishProgress(text) {
    const progressBar = document.querySelector("[data-upload-progress-bar]");
    if (progressBar) {
      progressBar.value = 100;
    }

    setSpinnerVisible(false);
    setCancelButtonVisible(false);
    showProgress(text);
  }

  // Restaura el botón de envío tras una acción.
  function restoreSubmitButton(button, originalText) {
    if (!button) {
      return;
    }

    button.disabled = false;
    button.classList.remove("btn-disabled");
    button.textContent = originalText;
  }

  // Bloquea el botón de envío durante una acción.
  function markSubmitButtonBusy(button) {
    if (!button) {
      return "";
    }

    const originalText = button.textContent;
    button.disabled = true;
    button.classList.add("btn-disabled");
    button.textContent = message("savingButton", "Guardando...");
    return originalText;
  }

  // Rellena la fila temporal del modelo en subida.
  function fillUploadingRow(row, foldName) {
    row.dataset.modelName = foldName;

    const nameCell = row.querySelector("[data-uploading-model-name]");
    const stateLabel = row.querySelector("[data-uploading-state-label]");
    const validationLabel = row.querySelector(
      "[data-uploading-validation-label]"
    );
    const actionLabel = row.querySelector("[data-uploading-action-label]");

    if (nameCell) {
      nameCell.textContent = foldName;
    }
    if (stateLabel) {
      stateLabel.textContent = message("uploadingState", "Subiendo...");
    }
    if (validationLabel) {
      validationLabel.textContent = message("pending", "Pendiente");
    }
    if (actionLabel) {
      actionLabel.textContent = message("uploadingAction", "Subiendo...");
    }
  }

  // Escapa valores usados en selectores CSS.
  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(value);
    }

    return value.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
  }

  // Crea o reutiliza la fila temporal de subida.
  function showUploadingRow(foldName) {
    if (!foldName) {
      return null;
    }

    const existingSelector = `tr[data-model-row][data-model-name="${cssEscape(
      foldName
    )}"]`;
    const existingRow = document.querySelector(existingSelector);
    if (existingRow) {
      return existingRow;
    }

    const body = document.querySelector("[data-model-table-body]");
    const template = document.getElementById("uploading-model-row-template");
    if (!body || !template) {
      return null;
    }

    const fragment = template.content.cloneNode(true);
    const row = fragment.querySelector("tr[data-model-row]");
    if (!row) {
      return null;
    }

    fillUploadingRow(row, foldName);
    body.prepend(fragment);
    return body.querySelector(existingSelector);
  }

  // Elimina la fila temporal de la tabla.
  function removeTemporaryRow(row) {
    if (row && row.querySelector("[data-uploading-model-name]")) {
      row.remove();
    }
  }

  // Interpreta la respuesta JSON de una petición.
  function parseJsonResponse(xhr) {
    try {
      return JSON.parse(xhr.responseText || "{}");
    } catch (_error) {
      return {
        ok: false,
        message: message(
          "networkError",
          "La conexión se ha interrumpido durante la subida."
        ),
      };
    }
  }

  // Limpia la referencia a la subida activa.
  function clearActiveUpload() {
    uploadInProgress = false;
    activeUploadXhr = null;
    setSpinnerVisible(false);
    setCancelButtonVisible(false);
  }

  // Restaura la interfaz cuando falla la subida.
  function handleUploadError(text, temporaryRow, submitButton, originalText) {
    clearActiveUpload();
    removeTemporaryRow(temporaryRow);
    restoreSubmitButton(submitButton, originalText);
    showProgress(text);
  }

  // Restaura la interfaz tras cancelar la subida.
  function handleUploadCancellation(temporaryRow, submitButton, originalText) {
    clearActiveUpload();
    removeTemporaryRow(temporaryRow);
    restoreSubmitButton(submitButton, originalText);
    hideProgressUi();
    showCancellationToast();
  }

  // Configura el botón de cancelación de subida.
  function setupCancelUploadButton() {
    const cancelButton = document.querySelector("[data-upload-cancel-button]");
    if (!cancelButton) {
      return;
    }

    cancelButton.addEventListener("click", () => {
      if (!activeUploadXhr || !uploadInProgress) {
        return;
      }

      cancelButton.disabled = true;
      showProgress(message("cancelling", "Cancelando subida..."));
      activeUploadXhr.abort();
    });
  }

  // Configura el formulario de subida con progreso AJAX.
  function setupUploadForm() {
    const uploadDialog = document.getElementById("upload-fold-modal");
    const uploadForm = document.getElementById("upload-fold-form");
    const submitButton = uploadForm?.querySelector('button[type="submit"]');

    document.querySelectorAll("[data-upload-fold-button]").forEach((button) => {
      button.addEventListener("click", () => {
        if (typeof uploadDialog.showModal === "function") {
          uploadDialog.showModal();
        }
      });
    });

    uploadForm?.addEventListener("submit", (event) => {
      if (!window.FormData || !window.XMLHttpRequest) {
        showProgress(message(
          "formDataUnsupported",
          "Tu navegador no permite mostrar el progreso de subida."
        ));
        return;
      }

      event.preventDefault();
      const originalText = markSubmitButtonBusy(submitButton);
      const formData = new FormData(uploadForm);
      const foldName = String(formData.get("fold_name") || "").trim();
      const temporaryRow = showUploadingRow(foldName);
      const xhr = new XMLHttpRequest();

      closeDialog(uploadDialog);
      uploadInProgress = true;
      activeUploadXhr = xhr;
      resetProgressUi();
      showProgress(message("submitting", "Enviando archivo al servidor..."));

      xhr.open("POST", uploadForm.action);
      xhr.setRequestHeader("Accept", "application/json");
      xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
      xhr.timeout = 0;

      xhr.upload.addEventListener("progress", (uploadEvent) => {
        if (uploadEvent.lengthComputable && uploadEvent.total > 0) {
          const percent = Math.round(
            (uploadEvent.loaded / uploadEvent.total) * 100
          );
          updateProgress(percent);
          return;
        }

        showProgress(message("uploading", "Subiendo archivo..."));
      });

      xhr.addEventListener("load", () => {
        const payload = parseJsonResponse(xhr);
        if (xhr.status < 200 || xhr.status >= 300 || payload.ok === false) {
          handleUploadError(
            payload.message || message("networkError", "Error de subida."),
            temporaryRow,
            submitButton,
            originalText
          );
          return;
        }

        clearActiveUpload();
        finishProgress(
          payload.message || message("received", "Modelo recibido.")
        );
        startRefreshLoop();
        window.setTimeout(() => {
          window.location.href = payload.redirect_url || window.location.href;
        }, 1200);
      });

      xhr.addEventListener("error", () => {
        handleUploadError(
          message("networkError", "La conexión se ha interrumpido."),
          temporaryRow,
          submitButton,
          originalText
        );
      });

      xhr.addEventListener("abort", () => {
        handleUploadCancellation(temporaryRow, submitButton, originalText);
      });

      xhr.send(formData);
    });
  }

  // Configura los modales de acciones sobre modelos.
  function setupActionModals() {
    const activateDialog = document.getElementById("activate-fold-modal");
    const activateName = document.getElementById("activate-fold-name");
    const activateInput = document.getElementById("activate-fold-input");

    document.querySelectorAll("[data-activate-fold-button]").forEach((button) => {
      button.addEventListener("click", () => {
        const foldName = button.dataset.foldName || "";
        activateName.textContent = foldName;
        activateInput.value = foldName;
        if (typeof activateDialog.showModal === "function") {
          activateDialog.showModal();
        }
      });
    });

    const deleteDialog = document.getElementById("delete-fold-modal");
    const deleteName = document.getElementById("delete-fold-name");
    const deleteInput = document.getElementById("delete-fold-input");

    document.querySelectorAll("[data-delete-fold-button]").forEach((button) => {
      button.addEventListener("click", () => {
        const foldName = button.dataset.foldName || "";
        deleteName.textContent = foldName;
        deleteInput.value = foldName;
        if (typeof deleteDialog.showModal === "function") {
          deleteDialog.showModal();
        }
      });
    });

    const renameDialog = document.getElementById("rename-fold-modal");
    const renameCurrentName = document.getElementById("rename-current-name");
    const renameNewName = document.getElementById("rename-new-name");

    document.querySelectorAll("[data-rename-fold-button]").forEach((button) => {
      button.addEventListener("click", () => {
        const currentName = button.dataset.currentName || "";
        renameCurrentName.value = currentName;
        renameNewName.value = currentName;
        if (typeof renameDialog.showModal === "function") {
          renameDialog.showModal();
        }
      });
    });
  }

  window.addEventListener("beforeunload", (event) => {
    if (!uploadInProgress) {
      return;
    }

    event.preventDefault();
    event.returnValue = message(
      "leaveWarning",
      "La subida del modelo sigue en curso. Si sales ahora, se cancelará."
    );
  });

  document.addEventListener("DOMContentLoaded", () => {
    if (config.hasRefreshingModels) {
      startRefreshLoop();
    }

    setupUploadForm();
    setupCancelUploadButton();
    setupActionModals();
  });
})();
