/**
 * Lógica de interfaz de la vista principal.
 *
 * Gestiona la selección de imágenes, la previsualización local, el envío del
 * formulario, el dibujado de trazas y la descarga de resultados.
 *
 * Autor: Marcos Zamorano Lasso
 * Versión: 1.0
 */
document.addEventListener("DOMContentLoaded", () => {
  const CFG = window.TRACES_APP || {};
  const serverHasImage = !!CFG.serverHasImage;
  const autoDrawTraces = !!CFG.autoDrawTraces;

  const I18N = Object.assign(
    {
      noFileChosen: "Ningún archivo seleccionado",
      statusNoImage: "Estado: ninguna imagen cargada. Inserta una imagen para empezar.",
      statusUploaded: "Estado: imagen cargada. Pulsa «Calcular trazas».",
      badgeNoImage: "Sin imagen",
      badgeUploaded: "Lista para calcular",
      badgeTracesCalculated: "Trazas calculadas",
    },
    CFG.i18n || {}
  );

  const tracesCheckbox = document.getElementById("traces-drawn-checkbox");
  if (tracesCheckbox) tracesCheckbox.checked = false;

  if (tracesCheckbox) {
    tracesCheckbox.addEventListener("change", () => {
      if (!lastTraces) {
        tracesCheckbox.checked = false;
        return;
      }

      if (tracesCheckbox.checked) {
        canvas.classList.remove("hidden");

        if (img && img.complete && img.naturalWidth > 0) {
          drawTracesFromData(lastTraces.xs, lastTraces.ys);
        } else if (img) {
          img.addEventListener(
            "load",
            () => drawTracesFromData(lastTraces.xs, lastTraces.ys),
            { once: true }
          );
        }
      } else {
        clearTracesOverlay();
      }
    });
  }

  const statusEl = document.getElementById("status-message");
  const statusBadgeEl = document.getElementById("status-badge");

  // Actualiza la insignia de estado de la vista principal.
  function setStatusBadge(state) {
    if (!statusBadgeEl) return;

    statusBadgeEl.classList.remove(
      "badge-warning",
      "badge-info",
      "badge-success",
      "badge-neutral"
    );

    if (state === "no_image") {
      statusBadgeEl.classList.add("badge-warning");
      statusBadgeEl.textContent = I18N.badgeNoImage;
      return;
    }

    if (state === "image_uploaded") {
      statusBadgeEl.classList.add("badge-info");
      statusBadgeEl.textContent = I18N.badgeUploaded;
      return;
    }

    if (state === "traces_calculated") {
      statusBadgeEl.classList.add("badge-success");
      statusBadgeEl.textContent = I18N.badgeTracesCalculated;
    }
  }

  const downloadBtn = document.getElementById("download-btn");

  // Activa o bloquea la descarga de resultados.
  function setDownloadEnabled(enabled) {
    if (!downloadBtn) return;

    if (enabled) {
      downloadBtn.disabled = false;
      downloadBtn.classList.remove("btn-disabled");
      downloadBtn.classList.add("btn-primary");
    } else {
      downloadBtn.disabled = true;
      downloadBtn.classList.remove("btn-primary");
      downloadBtn.classList.add("btn-disabled");
    }
  }

  setDownloadEnabled(false);

  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      if (downloadBtn.disabled) return;
      const url = downloadBtn.dataset.downloadUrl;
      if (url) window.location.href = url;
    });
  }

  const pipelineForm = document.getElementById("pipeline-form");
  const calculandoModal = document.getElementById("calculando-modal");
  const deleteForm = document.getElementById("delete-form");

  // Abre el modal de carga del procesamiento.
  function openLoadingModal() {
    if (!calculandoModal) return;
    if (typeof calculandoModal.showModal === "function") {
      calculandoModal.showModal();
    } else {
      calculandoModal.classList.add("modal-open");
    }
  }

  if (pipelineForm) {
    pipelineForm.addEventListener("submit", () => {
      openLoadingModal();
    });
  }

  const img = document.getElementById("main-image");
  const canvas = document.getElementById("traces-canvas");
  const placeholder = document.getElementById("placeholder");

  const imageFrame = document.getElementById("image-frame");
  const imageInput = document.getElementById("image-input");
  const selectedFileName = document.getElementById("selected-file-name");

  let localPreviewUrl = null;

  let lastTraces = null;

  // Limpia el lienzo de trazas dibujadas.
  function clearTracesOverlay() {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  // Comprueba si deben redibujarse las trazas visibles.
  function shouldRedrawVisibleTraces() {
    return !!(
      lastTraces &&
      tracesCheckbox &&
      tracesCheckbox.checked &&
      img &&
      img.complete &&
      img.naturalWidth > 0
    );
  }

  // Ajusta el lienzo y redibuja las trazas visibles.
  function resizeCanvasAndRedrawTraces() {
    resizeCanvas();
    if (!shouldRedrawVisibleTraces()) return;
    canvas.classList.remove("hidden");
    drawTracesFromData(lastTraces.xs, lastTraces.ys);
  }

  let resizeRedrawFrame = null;

  // Programa un reajuste del lienzo en el siguiente ciclo.
  function scheduleCanvasResizeAndRedraw() {
    if (resizeRedrawFrame) cancelAnimationFrame(resizeRedrawFrame);
    resizeRedrawFrame = requestAnimationFrame(() => {
      resizeRedrawFrame = null;
      resizeCanvasAndRedrawTraces();
    });
  }

  // Dibuja las trazas recibidas sobre el canvas.
  function drawTracesFromData(xs, ys) {
    if (!img || !canvas) return;

    resizeCanvas();
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const scaleX = canvas.width / img.naturalWidth;
    const scaleY = canvas.height / img.naturalHeight;

    ctx.fillStyle = "#ff0000";

    for (let i = 0; i < xs.length; i++) {
      ctx.fillRect(xs[i] * scaleX, ys[i] * scaleY, 1, 1);
    }
  }

  // Abre el selector de archivos de imagen.
  function openImagePicker() {
    if (!imageInput) return;
    imageInput.click();
  }

  // Sincroniza el tamaño del canvas con la imagen.
  function resizeCanvas() {
    if (!img || !canvas) return;
    canvas.width = img.clientWidth;
    canvas.height = img.clientHeight;
  }

  if (img && canvas) {
    img.addEventListener("load", scheduleCanvasResizeAndRedraw);
    window.addEventListener("resize", scheduleCanvasResizeAndRedraw);
    resizeCanvas();
  }

  // Carga y dibuja las trazas desde el JSON del servidor.
  async function drawTracesFromJson() {
    if (!img || !canvas) return;

    resizeCanvas();
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    try {
      const response = await fetch("/traces", { cache: "no-store" });
      const data = await response.json();

      const xs = data.xs || [];
      const ys = data.ys || [];

      lastTraces = { xs, ys };

      drawTracesFromData(xs, ys);

      if (tracesCheckbox) {
        tracesCheckbox.disabled = false;
        tracesCheckbox.checked = true;
      }
      setDownloadEnabled(true);
    } catch (e) {
      console.error("Error dibujando trazas:", e);
    }
  }

  // Dibuja automáticamente las trazas si la página lo indica.
  function maybeAutoDraw() {
    if (!autoDrawTraces) return;
    if (!img || !canvas) return;

    canvas.classList.remove("hidden");

    if (img.complete && img.naturalWidth > 0) {
      drawTracesFromJson();
    } else {
      img.addEventListener("load", () => drawTracesFromJson(), { once: true });
    }
  }

  maybeAutoDraw();

  // Limpia la previsualización local de imagen.
  function clearPreviewOnly() {
    if (localPreviewUrl) {
      URL.revokeObjectURL(localPreviewUrl);
      localPreviewUrl = null;
    }
    if (imageInput) imageInput.value = "";
    if (selectedFileName) selectedFileName.textContent = I18N.noFileChosen;

    if (canvas) {
      const ctx = canvas.getContext("2d");
      if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    if (tracesCheckbox) tracesCheckbox.checked = false;
    lastTraces = null;
    if (tracesCheckbox) tracesCheckbox.disabled = true;
    setDownloadEnabled(false);

    if (!serverHasImage) {
      if (img) {
        img.src = "";
        img.classList.add("hidden");
      }
      if (canvas) canvas.classList.add("hidden");
      if (placeholder) placeholder.classList.remove("hidden");
      if (statusEl) {
        statusEl.textContent = I18N.statusNoImage;
        setStatusBadge("no_image");
      }
    }
  }

  // Actualiza el estado visual del área de arrastre.
  function setDropzoneState(state) {
    if (!imageFrame) return;

    imageFrame.classList.remove(
      "border-base-300",
      "border-primary",
      "border-success",
      "border-error",
      "bg-primary/5",
      "bg-success/5",
      "bg-error/5"
    );

    if (state === "active") {
      imageFrame.classList.add("border-primary", "bg-primary/5");
    } else if (state === "success") {
      imageFrame.classList.add("border-success", "bg-success/5");
    } else if (state === "error") {
      imageFrame.classList.add("border-error", "bg-error/5");
    } else {
      imageFrame.classList.add("border-base-300");
    }
  }

  // Valida que el archivo seleccionado sea una imagen admitida.
  function isValidImageFile(file) {
    if (!file) return false;
    const okTypes = ["image/png", "image/jpeg"];
    if (okTypes.includes(file.type)) return true;
    const name = (file.name || "").toLowerCase();
    return name.endsWith(".png") || name.endsWith(".jpg") || name.endsWith(".jpeg");
  }

  // Muestra la previsualización local de una imagen.
  function previewFile(file) {
    if (!file) return;

    if (selectedFileName) selectedFileName.textContent = file.name;

    if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
    localPreviewUrl = URL.createObjectURL(file);

    if (placeholder) placeholder.classList.add("hidden");
    if (img) {
      img.src = localPreviewUrl;
      img.classList.remove("hidden");
    }
    if (canvas) canvas.classList.remove("hidden");

    if (canvas) {
      const ctx = canvas.getContext("2d");
      if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    lastTraces = null;
    if (tracesCheckbox) {
      tracesCheckbox.checked = false;
      tracesCheckbox.disabled = true;
    }
    setDownloadEnabled(false);
    if (statusEl) statusEl.textContent = I18N.statusUploaded;
    setStatusBadge("image_uploaded");

    if (img && canvas) {
      if (img.complete && img.naturalWidth > 0) resizeCanvas();
      else img.addEventListener("load", resizeCanvas, { once: true });
    }
  }

  if (imageInput) {
    imageInput.addEventListener("change", () => {
      if (!imageInput.files || imageInput.files.length === 0) return;
      previewFile(imageInput.files[0]);
    });
  }

  if (deleteForm) {
    deleteForm.addEventListener("submit", (e) => {
      const hasLocalPreview =
        imageInput && imageInput.files && imageInput.files.length > 0;
      if (!serverHasImage && hasLocalPreview) {
        e.preventDefault();
        clearPreviewOnly();
        return;
      }

      if (tracesCheckbox) tracesCheckbox.checked = false;
      setDownloadEnabled(false);
    });
  }

  if (imageFrame) {
    let dragDepth = 0;

    // Cancela el comportamiento por defecto del navegador.
    const prevent = (e) => {
      e.preventDefault();
      e.stopPropagation();
    };

    imageFrame.addEventListener("dragenter", (e) => {
      prevent(e);
      dragDepth++;
      setDropzoneState("active");
    });

    imageFrame.addEventListener("dragover", (e) => {
      prevent(e);
      setDropzoneState("active");
    });

    imageFrame.addEventListener("dragleave", (e) => {
      prevent(e);
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) setDropzoneState("idle");
    });

    imageFrame.addEventListener("drop", (e) => {
      prevent(e);
      dragDepth = 0;

      const file =
        e.dataTransfer && e.dataTransfer.files ? e.dataTransfer.files[0] : null;

      if (!isValidImageFile(file)) {
        setDropzoneState("error");
        setTimeout(() => setDropzoneState("idle"), 900);
        return;
      }

      if (imageInput) {
        const dt = new DataTransfer();
        dt.items.add(file);
        imageInput.files = dt.files;
      }

      previewFile(file);
      setDropzoneState("success");
      setTimeout(() => setDropzoneState("idle"), 700);
    });

    imageFrame.addEventListener("click", (e) => {
      if (placeholder && placeholder.classList.contains("hidden")) return;
      if (e.target.closest("button, a, input, label")) return;
      openImagePicker();
    });

    document.addEventListener("dragover", prevent);
    document.addEventListener("drop", (e) => {
      if (!imageFrame.contains(e.target)) prevent(e);
    });
  }
});
