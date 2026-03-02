/**
 * Lógica de interfaz de la vista principal.
 *
 * Este archivo gestiona la previsualización local de imágenes, la interacción
 * de drag and drop, el estado visual de la página, la apertura del modal de
 * carga, el dibujado de trazas sobre el canvas y la habilitación de la
 * descarga de resultados.
 *
 * Lee su configuración desde window.TRACES_APP, inyectado por la
 * plantilla del servidor.
 *
 * Autor: Marcos Zamorano Lasso
 * Versión: 0.1
 */

document.addEventListener("DOMContentLoaded", () => {
  const CFG = window.TRACES_APP || {};
  const serverHasImage = !!CFG.serverHasImage;
  const autoDrawTraces = !!CFG.autoDrawTraces;

  // Cadenas traducidas recibidas desde la plantilla.
  const I18N = Object.assign(
    {
      noFileChosen: "Ningún archivo seleccionado",
      statusNoImage: "Estado: ninguna imagen cargada. Inserta una imagen para empezar.",
      statusUploaded: "Estado: imagen cargada. Pulsa «Calcular trazas».",
    },
    CFG.i18n || {}
  );

  // El estado del checkbox se reinicia en cada carga de página.
  const tracesCheckbox = document.getElementById("traces-drawn-checkbox");
  if (tracesCheckbox) tracesCheckbox.checked = false;

  const statusEl = document.getElementById("status-message");

  const downloadBtn = document.getElementById("download-btn");

  /**
   * Activa o desactiva el botón de descarga y ajusta su estado visual.
   *
   * @param {boolean} enabled Indica si la descarga debe estar disponible.
   */
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

  // La descarga solo se habilita cuando ya existen trazas dibujadas.
  setDownloadEnabled(false);

  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      if (downloadBtn.disabled) return;
      const url = downloadBtn.dataset.downloadUrl;
      if (url) window.location.href = url;
    });
  }

  // Modal de carga durante el envío del pipeline.
  const pipelineForm = document.getElementById("pipeline-form");
  const calculandoModal = document.getElementById("calculando-modal");
  const deleteForm = document.getElementById("delete-form");

  /**
   * Abre el modal de cálculo usando la API nativa si está disponible.
   */
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

  // Elementos principales de imagen y canvas.
  const img = document.getElementById("main-image");
  const canvas = document.getElementById("traces-canvas");
  const placeholder = document.getElementById("placeholder");

  const imageFrame = document.getElementById("image-frame");
  const imageInput = document.getElementById("image-input");
  const selectedFileName = document.getElementById("selected-file-name");

  let localPreviewUrl = null;

  /**
   * Abre el selector de archivos asociado al input de imagen.
   */
  function openImagePicker() {
    if (!imageInput) return;
    imageInput.click();
  }

  /**
   * Ajusta el tamaño del canvas al tamaño visible de la imagen.
   *
   * El canvas trabaja superpuesto a la imagen, por lo que ambos deben
   * compartir dimensiones en pantalla.
   */
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

  /**
   * Recupera las trazas desde el backend y las dibuja sobre el canvas.
   *
   * Las coordenadas se escalan en función del tamaño visible de la imagen para
   * mantener la correspondencia entre el tamaño original y la representación
   * mostrada en pantalla.
   */
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

      // Mantiene el color de trazado definido para la superposición.
      ctx.fillStyle = "#ff0000";

      for (let i = 0; i < xs.length; i++) {
        ctx.fillRect(xs[i] * scaleX, ys[i] * scaleY, 1, 1);
      }

      if (tracesCheckbox) tracesCheckbox.checked = true;
      setDownloadEnabled(true);
    } catch (e) {
      console.error("Error dibujando trazas:", e);
    }
  }

  /**
   * Lanza el dibujado automático si el servidor indica que ya hay trazas
   * calculadas para la imagen actual.
   */
  function maybeAutoDraw() {
    if (!autoDrawTraces) return;
    if (!img || !canvas) return;

    canvas.classList.remove("hidden");

    // Si la imagen ya está cargada desde caché, el evento load puede haber ocurrido.
    if (img.complete && img.naturalWidth > 0) {
      drawTracesFromJson();
    } else {
      img.addEventListener("load", () => drawTracesFromJson(), { once: true });
    }
  }

  maybeAutoDraw();

  /**
   * Limpia únicamente la previsualización local y restablece el estado visual.
   *
   * No realiza ninguna operación contra el backend.
   */
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
    setDownloadEnabled(false);

    // Solo se vuelve al placeholder si no existe una imagen persistida en servidor.
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

  /**
   * Actualiza el aspecto visual de la zona de carga según su estado.
   *
   * @param {"idle"|"active"|"success"|"error"} state Estado visual a aplicar.
   */
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

  /**
   * Comprueba si el fichero recibido tiene un formato de imagen admitido.
   *
   * @param {File|null|undefined} file Fichero a validar.
   * @returns {boolean} true si el fichero parece una imagen PNG o JPEG.
   */
  function isValidImageFile(file) {
    if (!file) return false;
    const okTypes = ["image/png", "image/jpeg"];
    if (okTypes.includes(file.type)) return true;
    const name = (file.name || "").toLowerCase();
    return name.endsWith(".png") || name.endsWith(".jpg") || name.endsWith(".jpeg");
  }

  /**
   * Genera la previsualización local de la imagen seleccionada.
   *
   * Reinicia el canvas y el estado asociado a trazas previas, ya que la
   * selección de una nueva imagen invalida cualquier superposición anterior.
   *
   * @param {File} file Fichero de imagen a mostrar en local.
   */
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
    if (tracesCheckbox) tracesCheckbox.checked = false;
    setDownloadEnabled(false);
    if (statusEl) statusEl.textContent = I18N.statusUploaded;

    // Fuerza el ajuste del canvas incluso si la imagen se resuelve muy rápido.
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

  // Si solo existe una preview local y no hay imagen persistida, el borrado se
  // resuelve en cliente sin enviar la petición al backend.
  if (deleteForm) {
    deleteForm.addEventListener("submit", (e) => {
      const hasLocalPreview =
        imageInput && imageInput.files && imageInput.files.length > 0;
      if (!serverHasImage && hasLocalPreview) {
        e.preventDefault();
        clearPreviewOnly();
        return;
      }

      // Si el borrado sí llega al backend, se reinicia el estado visual local.
      if (tracesCheckbox) tracesCheckbox.checked = false;
      setDownloadEnabled(false);
    });
  }

  // Gestión de drag and drop para la selección de imágenes.
  if (imageFrame) {
    let dragDepth = 0;

    /**
     * Cancela el comportamiento por defecto del navegador durante el drag and drop.
     *
     * @param {DragEvent} e Evento de arrastre.
     */
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

      // Se replica el fichero en el input para mantener un único origen de datos.
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

    // Evita que el navegador intente abrir el archivo si se suelta fuera del área.
    document.addEventListener("dragover", prevent);
    document.addEventListener("drop", (e) => {
      if (!imageFrame.contains(e.target)) prevent(e);
    });
  }
});