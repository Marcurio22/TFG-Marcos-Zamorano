/* ==========================================================================
Archivo: index.js
Descripción:
  Lógica frontend del index: preview local, drag&drop, modal calculando,
  dibujo de trazas y estado.
  Lee configuración desde window.TRACES_APP (inyectada por index.html).
========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
  const CFG = window.TRACES_APP || {};
  const serverHasImage = !!CFG.serverHasImage;
  const autoDrawTraces = !!CFG.autoDrawTraces;

  // Flask-Babel (strings ya traducidas vienen desde CFG.i18n)
  const I18N = Object.assign(
    {
      noFileChosen: "Ningún archivo seleccionado",
      statusNoImage: "Estado: ninguna imagen cargada. Inserta una imagen para empezar.",
      statusUploaded: "Estado: imagen cargada. Pulsa «Calcular trazas».",
    },
    CFG.i18n || {}
  );

  // Reiniciar el checkbox siempre al cargar la página
  const tracesCheckbox = document.getElementById("traces-drawn-checkbox");
  if (tracesCheckbox) tracesCheckbox.checked = false;

  const statusEl = document.getElementById("status-message");

  // Descargar resultados
  const downloadBtn = document.getElementById("download-btn");

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

  // Estado inicial
  setDownloadEnabled(false);

  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      if (downloadBtn.disabled) return;
      const url = downloadBtn.dataset.downloadUrl;
      if (url) window.location.href = url;
    });
  }

  /* -------------------------------------------------------------
     1) Mostrar modal "Calculando..."
  -------------------------------------------------------------- */
  const pipelineForm = document.getElementById("pipeline-form");
  const calculandoModal = document.getElementById("calculando-modal");
  const deleteForm = document.getElementById("delete-form");

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

  /* -------------------------------------------------------------
     2) Ajustar tamaño del canvas según la imagen
  -------------------------------------------------------------- */
  const img = document.getElementById("main-image");
  const canvas = document.getElementById("traces-canvas");
  const placeholder = document.getElementById("placeholder");

  const imageFrame = document.getElementById("image-frame");
  const imageInput = document.getElementById("image-input");
  const selectedFileName = document.getElementById("selected-file-name");

  let localPreviewUrl = null;

  function openImagePicker() {
    if (!imageInput) return;
    imageInput.click();
  }

  function resizeCanvas() {
    if (!img || !canvas) return;
    canvas.width = img.clientWidth;
    canvas.height = img.clientHeight;
  }

  if (img && canvas) {
    img.addEventListener("load", resizeCanvas);
    window.addEventListener("resize", resizeCanvas);
    resizeCanvas();
  }

  /* -------------------------------------------------------------
     3) Dibujar trazas desde /traces
  -------------------------------------------------------------- */
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

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const scaleX = canvas.width / img.naturalWidth;
      const scaleY = canvas.height / img.naturalHeight;

      // Rojo fuerte como en la versión inicial
      ctx.fillStyle = "#ff0000";

      for (let i = 0; i < xs.length; i++) {
        ctx.fillRect(xs[i] * scaleX, ys[i] * scaleY, 1.5, 1.5);
      }

      // Marcar checkbox cuando las trazas se han dibujado
      if (tracesCheckbox) tracesCheckbox.checked = true;
      setDownloadEnabled(true);
    } catch (e) {
      console.error("Error dibujando trazas:", e);
    }
  }

  /* -------------------------------------------------------------
     4) Auto-dibujado tras volver del cálculo
  -------------------------------------------------------------- */
  function maybeAutoDraw() {
    if (!autoDrawTraces) return;
    if (!img || !canvas) return;

    canvas.classList.remove("hidden");

    // Caso cacheado: el evento load ya ocurrió
    if (img.complete && img.naturalWidth > 0) {
      drawTracesFromJson();
    } else {
      img.addEventListener("load", () => drawTracesFromJson(), { once: true });
    }
  }

  maybeAutoDraw();

  /* -------------------------------------------------------------
     5) Lógica de subida de imagen
  -------------------------------------------------------------- */
  function clearPreviewOnly() {
    // Limpia preview local sin tocar backend.
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
    setDownloadEnabled(false);

    // Si no hay imagen en backend, volvemos a placeholder.
    if (!serverHasImage) {
      if (img) {
        img.src = "";
        img.classList.add("hidden");
      }
      if (canvas) canvas.classList.add("hidden");
      if (placeholder) placeholder.classList.remove("hidden");
      if (statusEl) {
        statusEl.textContent = I18N.statusNoImage;
      }
    }
  }

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

  function isValidImageFile(file) {
    if (!file) return false;
    const okTypes = ["image/png", "image/jpeg"];
    if (okTypes.includes(file.type)) return true;
    const name = (file.name || "").toLowerCase();
    return name.endsWith(".png") || name.endsWith(".jpg") || name.endsWith(".jpeg");
  }

  function previewFile(file) {
    if (!file) return;

    // Nombre de fichero visible
    if (selectedFileName) selectedFileName.textContent = file.name;

    // Preview local
    if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
    localPreviewUrl = URL.createObjectURL(file);

    if (placeholder) placeholder.classList.add("hidden");
    if (img) {
      img.src = localPreviewUrl;
      img.classList.remove("hidden");
    }
    if (canvas) canvas.classList.remove("hidden");

    // Reiniciamos trazas/canvas al cambiar de imagen
    if (canvas) {
      const ctx = canvas.getContext("2d");
      if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    if (tracesCheckbox) tracesCheckbox.checked = false;
    setDownloadEnabled(false);
    if (statusEl) statusEl.textContent = I18N.statusUploaded;

    // Asegurar resize aunque la imagen cargue muy rápido
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

  // BORRAR: si estamos en preview local y no hay imagen en backend, borramos sólo frontend.
  if (deleteForm) {
    deleteForm.addEventListener("submit", (e) => {
      const hasLocalPreview =
        imageInput && imageInput.files && imageInput.files.length > 0;
      if (!serverHasImage && hasLocalPreview) {
        e.preventDefault();
        clearPreviewOnly();
        return;
      }

      // Si se va a borrar en backend, al menos reiniciamos el checkbox.
      if (tracesCheckbox) tracesCheckbox.checked = false;
      setDownloadEnabled(false);
    });
  }

  // Listeners de drag y drop para subida de imágenes
  if (imageFrame) {
    let dragDepth = 0;

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

    // Evita que el navegador abra el archivo si se suelta fuera del frame
    document.addEventListener("dragover", prevent);
    document.addEventListener("drop", (e) => {
      if (!imageFrame.contains(e.target)) prevent(e);
    });
  }
});