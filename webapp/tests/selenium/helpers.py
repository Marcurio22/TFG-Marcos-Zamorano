"""
==============================================================================
Helpers comunes para pruebas funcionales con Selenium.

Contiene utilidades de espera, autenticación, creación de datos y generación de
imágenes usadas por los flujos de navegador.

Autor: Marcos Zamorano Lasso
Versión: 0.1
==============================================================================
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path


from PIL import Image
from werkzeug.security import generate_password_hash

from trazasytrazadas.db import db
from trazasytrazadas.models import Foto, Modelo, Parcela, Usuario


PASSWORD = "Password1!"


def by_css():
    """Devuelve el selector CSS de Selenium evitando imports globales."""
    from selenium.webdriver.common.by import By

    return By.CSS_SELECTOR


def wait_class(timeout: int = 8):
    """Construye una espera explícita de Selenium."""
    from selenium.webdriver.support.ui import WebDriverWait

    return WebDriverWait


def expected_conditions():
    """Devuelve el módulo de condiciones esperadas de Selenium."""
    from selenium.webdriver.support import expected_conditions as ec

    return ec


def css(driver, selector: str, timeout: int = 8):
    """Espera y devuelve un elemento localizado por selector CSS."""
    wait = wait_class()(driver, timeout)
    return wait.until(
        expected_conditions().presence_of_element_located(
            (by_css(), selector),
        )
    )


def clickable(driver, selector: str, timeout: int = 8):
    """Espera y devuelve un elemento clicable por selector CSS."""
    wait = wait_class()(driver, timeout)
    return wait.until(
        expected_conditions().element_to_be_clickable((by_css(), selector))
    )


def visible_css(driver, selector: str, timeout: int = 8):
    """Espera y devuelve un elemento visible por selector CSS."""
    wait = wait_class()(driver, timeout)
    return wait.until(
        expected_conditions().visibility_of_element_located(
            (by_css(), selector),
        )
    )


def _dispatch_map_click(driver, map_element, x_pos: int, y_pos: int) -> None:
    """Dispara un clic de ratón realista sobre el mapa Leaflet."""
    driver.execute_script(
        """
        const target = arguments[0];
        const xPos = arguments[1];
        const yPos = arguments[2];
        const rect = target.getBoundingClientRect();
        const clientX = rect.left + xPos;
        const clientY = rect.top + yPos;
        const eventTarget = document.elementFromPoint(clientX, clientY)
          || target;
        const options = {
          bubbles: true,
          cancelable: true,
          view: window,
          button: 0,
          clientX,
          clientY,
          screenX: window.screenX + clientX,
          screenY: window.screenY + clientY,
        };
        eventTarget.dispatchEvent(new MouseEvent('mousemove', options));
        eventTarget.dispatchEvent(
          new MouseEvent('mousedown', { ...options, buttons: 1 })
        );
        eventTarget.dispatchEvent(
          new MouseEvent('mouseup', { ...options, buttons: 0 })
        );
        eventTarget.dispatchEvent(new MouseEvent('click', options));
        """,
        map_element,
        x_pos,
        y_pos,
    )


def zoom_map_to_detail(driver, clicks: int = 13) -> None:
    """Acerca Leaflet hasta un nivel de detalle alto sobre España."""
    visible_css(driver, ".leaflet-container")
    for _index in range(clicks):
        zoom_button = clickable(driver, ".leaflet-control-zoom-in")
        if "leaflet-disabled" in zoom_button.get_attribute("class"):
            break
        zoom_button.click()
        time.sleep(0.05)


def select_map_area_near_center(driver, selector: str = "#visor-map") -> None:
    """Selecciona un rectángulo pequeño tras acercarse sobre España."""
    zoom_map_to_detail(driver)
    map_element = css(driver, selector)
    width, height = driver.execute_script(
        """
        const rect = arguments[0].getBoundingClientRect();
        return [Math.floor(rect.width), Math.floor(rect.height)];
        """,
        map_element,
    )
    center_x = max(80, width // 2)
    center_y = max(80, height // 2)
    for x_pos, y_pos in (
        (center_x - 12, center_y - 12),
        (center_x + 12, center_y + 12),
    ):
        _dispatch_map_click(driver, map_element, x_pos, y_pos)


def wait_for_map_selection(driver, timeout: int = 8) -> None:
    """Espera a que Leaflet pinte los dos marcadores de selección."""
    wait = wait_class()(driver, timeout)
    wait.until(
        lambda web_driver: len(
            web_driver.find_elements(by_css(), ".leaflet-marker-icon")
        ) >= 2
    )


def wait_for_text(driver, text: str, timeout: int = 8) -> None:
    """Espera a que un texto aparezca en el cuerpo de la página."""
    wait = wait_class()(driver, timeout)
    wait.until(
        expected_conditions().text_to_be_present_in_element(
            (by_css(), "body"),
            text,
        )
    )


def wait_for_url_contains(driver, fragment: str, timeout: int = 8) -> None:
    """Espera a que la URL del navegador contenga un fragmento."""
    wait = wait_class()(driver, timeout)
    wait.until(expected_conditions().url_contains(fragment))


def wait_for_grid_ready(driver, timeout: int = 12) -> None:
    """Espera a que el visor muestre teselas descargables."""
    wait = wait_class()(driver, timeout)
    wait.until(
        lambda web_driver: "Tesela" in css(
            web_driver,
            "#download-list",
        ).text
    )


def wait_for_download(
    download_dir: Path,
    suffix: str,
    timeout: int = 12,
) -> Path:
    """Espera a que Chrome complete una descarga con el sufijo dado."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        partials = list(download_dir.glob("*.crdownload"))
        matches = [
            path for path in download_dir.iterdir()
            if path.suffix == suffix
        ]
        completed = [path for path in matches if path.stat().st_size > 0]
        if completed and not partials:
            return completed[0]
        time.sleep(0.1)
    raise AssertionError(f"No se completó ninguna descarga {suffix}.")


def open_visor_controls_modal(driver):
    """Abre el modal de controles del visor y espera a que sea visible."""
    clickable(driver, "#open-controls-btn").click()
    modal = css(driver, "#visor-controls-modal")
    wait = wait_class()(driver, 8)
    wait.until(lambda _driver: modal.get_attribute("open") is not None)
    return modal


def fill(driver, name: str, value: str) -> None:
    """Rellena un campo de formulario identificado por su atributo name."""
    element = css(driver, f"[name='{name}']")
    element.clear()
    element.send_keys(value)


def submit(driver, selector: str) -> None:
    """Envía un formulario o botón tras esperar a que sea clicable."""
    clickable(driver, selector).click()


def select_option(driver, selector: str, value: str) -> None:
    """Selecciona una opción de un campo select por valor."""
    from selenium.webdriver.support.ui import Select

    Select(css(driver, selector)).select_by_value(value)


def wait_for_authenticated_user(
    driver,
    username: str,
    timeout: int = 8,
) -> None:
    """Espera a que la página renderice al usuario autenticado."""
    wait = wait_class()(driver, timeout)
    wait.until(lambda web_driver: "/login" not in web_driver.current_url)
    wait.until(
        lambda web_driver: username in web_driver.page_source
        or "Has iniciado sesión correctamente" in web_driver.page_source
    )


def login_through_ui(driver, base_url: str, username: str) -> None:
    """Inicia sesión usando el formulario real de login."""
    driver.get(f"{base_url}/login")
    fill(driver, "nombre_usuario", username)
    fill(driver, "contrasena", PASSWORD)
    submit(driver, "input[type='submit']")
    wait_for_authenticated_user(driver, username)


def create_user(
    app,
    *,
    username: str,
    email: str,
    role: str = "user",
) -> int:
    """Crea un usuario persistido para flujos Selenium."""
    with app.app_context():
        user = Usuario(
            nombre_usuario=username,
            correo_electronico=email,
            telefono=None,
            contrasena=generate_password_hash(PASSWORD),
            rol=role,
        )
        db.session.add(user)
        db.session.commit()
        return int(user.usuario_id)


def create_image_file(tmp_path: Path, name: str = "imagen.jpg") -> Path:
    """Genera una imagen JPEG válida para pruebas de subida."""
    path = tmp_path / name
    image = Image.new("RGB", (32, 24), color=(35, 90, 160))
    image.save(path, format="JPEG")
    return path


def fake_jpeg_bytes() -> bytes:
    """Genera bytes JPEG válidos para teselas de colección."""
    image = Image.new("RGB", (16, 16), color=(80, 120, 60))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _zone_state_from_photo_states(photo_states: tuple[str, ...]) -> str:
    """Calcula el estado agregado de una colección de Selenium."""
    if photo_states and all(state == "completed" for state in photo_states):
        return "completed"
    if any(state == "failed" for state in photo_states):
        return "failed"
    if any(state == "processing" for state in photo_states):
        return "processing"
    return "pending"


def _write_collection_file(
    app,
    *,
    parcel_id: int,
    folder: str,
    filename: str,
    content: bytes,
) -> str:
    """Guarda un fichero de colección y devuelve su ruta relativa."""
    relative_path = f"parcelas/{parcel_id}/{folder}/{filename}"
    absolute_path = Path(app.config["COLLECTION_STORAGE_ROOT"])
    absolute_path = absolute_path / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_bytes(content)
    return relative_path


def _write_collection_traces(
    app,
    *,
    parcel_id: int,
    filename: str,
) -> str:
    """Guarda trazas JSON asociadas a una tesela completada."""
    content = json.dumps({"xs": [1, 4, 8], "ys": [2, 5, 9]}).encode()
    return _write_collection_file(
        app,
        parcel_id=parcel_id,
        folder="traces",
        filename=filename,
        content=content,
    )


def create_collection(
    app,
    *,
    user_id: int,
    name: str = "Colección Selenium",
    photo_states: tuple[str, ...] = ("pending", "processing"),
) -> int:
    """Crea una colección con teselas locales para probar la UI."""
    with app.app_context():
        parcel = Parcela(
            usuario_id=user_id,
            tamano_metros=100.0,
            pto_origen_latitud=42.365433,
            pto_origen_longitud=2.648456,
            pto_fin_latitud=42.363974,
            pto_fin_longitud=2.651460,
            fuente_id="pnoa2023",
            fuente_nombre="PNOA Máxima Actualidad",
            resolucion_solicitada=0.25,
            resolucion_real=0.25,
            ancho_tesela=1024,
            alto_tesela=640,
            estado=_zone_state_from_photo_states(photo_states),
            nombre_coleccion=name,
        )
        db.session.add(parcel)
        db.session.flush()
        parcel_id = int(parcel.parcela_id)

        for index, state in enumerate(photo_states, start=1):
            filename = f"tile_{index}.jpg"
            trace_filename = f"tile_{index}_traces.json"
            photo_path = _write_collection_file(
                app,
                parcel_id=parcel_id,
                folder="tiles",
                filename=filename,
                content=fake_jpeg_bytes(),
            )
            trace_path = None
            if state == "completed":
                trace_path = _write_collection_traces(
                    app,
                    parcel_id=parcel_id,
                    filename=trace_filename,
                )

            db.session.add(
                Foto(
                    parcela_id=parcel_id,
                    modelo_id=None,
                    fecha_foto="2026-05-20",
                    resolucion_valor=0.25,
                    resolucion_unidad="m/px",
                    longitud=2.648456 + index / 1000,
                    latitud=42.365433,
                    ruta_foto=photo_path,
                    ruta_trazas=trace_path,
                    trazas=1 if state == "completed" else 0,
                    estado=state,
                    mensaje_error=None,
                    iniciado_en=None,
                    finalizado_en=None,
                    numero_intentos=0,
                    tesela_id=f"r01_c{index:02d}",
                    indice_fila=1,
                    indice_columna=index,
                    nombre_archivo=filename,
                    ancho=1024,
                    alto=640,
                    limites_3857_json=json.dumps(
                        {"xmin": 0, "ymin": 0, "xmax": 1, "ymax": 1},
                    ),
                    limites_json=json.dumps(
                        {
                            "sur": 42.36,
                            "oeste": 2.64,
                            "norte": 42.37,
                            "este": 2.65,
                        },
                    ),
                )
            )

        db.session.commit()
        return parcel_id


def create_demo_model(
    app,
    name: str = "modelo_selenium.pt",
    *,
    active: bool = True,
    validation: str = "validado",
) -> None:
    """Crea un modelo visible en el panel admin."""
    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / name).write_bytes(b"modelo de prueba")
        db.session.add(
            Modelo(
                nombre_modelo=name,
                estado="activo" if active else "no_activo",
                validacion=validation,
            )
        )
        db.session.commit()
