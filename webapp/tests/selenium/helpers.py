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


def fill(driver, name: str, value: str) -> None:
    """Rellena un campo de formulario identificado por su atributo name."""
    element = css(driver, f"[name='{name}']")
    element.clear()
    element.send_keys(value)


def submit(driver, selector: str) -> None:
    """Envía un formulario o botón tras esperar a que sea clicable."""
    clickable(driver, selector).click()


def login_through_ui(driver, base_url: str, username: str) -> None:
    """Inicia sesión usando el formulario real de login."""
    driver.get(f"{base_url}/login")
    fill(driver, "nombre_usuario", username)
    fill(driver, "contrasena", PASSWORD)
    submit(driver, "input[type='submit']")
    wait_for_text(driver, "Has iniciado sesión correctamente")


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


def create_collection(
    app,
    *,
    user_id: int,
    name: str = "Colección Selenium",
    photo_states: tuple[str, ...] = ("pending", "processing"),
) -> int:
    """Crea una colección con teselas para probar la UI."""
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
            estado="processing",
            nombre_coleccion=name,
        )
        db.session.add(parcel)
        db.session.flush()

        for index, state in enumerate(photo_states, start=1):
            db.session.add(
                Foto(
                    parcela_id=int(parcel.parcela_id),
                    modelo_id=None,
                    fecha_foto="2026-05-20",
                    resolucion_valor=0.25,
                    resolucion_unidad="m/px",
                    longitud=2.648456 + index / 1000,
                    latitud=42.365433,
                    ruta_foto=f"/visor/download/tile?tile={index}",
                    ruta_trazas=None,
                    trazas=1 if state == "completed" else 0,
                    estado=state,
                    mensaje_error=None,
                    iniciado_en=None,
                    finalizado_en=None,
                    numero_intentos=0,
                    tesela_id=f"r01_c{index:02d}",
                    indice_fila=1,
                    indice_columna=index,
                    nombre_archivo=f"tile_{index}.jpg",
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
        return int(parcel.parcela_id)


def create_demo_model(app, name: str = "modelo_selenium.pt") -> None:
    """Crea un modelo validado visible en el panel admin."""
    with app.app_context():
        models_dir = Path(app.config["SEG_MODELS_DIR"])
        models_dir.mkdir(parents=True, exist_ok=True)
        (models_dir / name).write_bytes(b"modelo de prueba")
        db.session.add(
            Modelo(
                nombre_modelo=name,
                estado="activo",
                validacion="validado",
            )
        )
        db.session.commit()
