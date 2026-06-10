"""Fixtures de Selenium y servidor local para pruebas de navegador.

Autor: Marcos Zamorano Lasso
Versión: 1.0
"""

from __future__ import annotations

import os
import shutil
import socket
import threading
import time
from types import MethodType
import urllib.error
import urllib.request

import pytest
from werkzeug.serving import make_server


HOST = "127.0.0.1"


def pytest_addoption(parser):
    """Registra opciones de línea de comandos para Selenium."""
    group = parser.getgroup("selenium")
    group.addoption(
        "--selenium",
        action="store_true",
        default=False,
        help="Ejecuta los tests funcionales de navegador.",
    )
    group.addoption(
        "--selenium-headed",
        action="store_true",
        default=False,
        help="Abre Chrome con ventana visible durante los tests.",
    )
    group.addoption(
        "--selenium-browser-binary",
        default=os.environ.get("SELENIUM_BROWSER_BINARY", ""),
        help="Ruta opcional al binario de Chrome o Chromium.",
    )
    group.addoption(
        "--selenium-slow-ms",
        default=os.environ.get("SELENIUM_SLOW_MS", "0"),
        help="Milisegundos de pausa tras cada comando del navegador.",
    )
    group.addoption(
        "--selenium-final-wait",
        default=os.environ.get("SELENIUM_FINAL_WAIT", "0"),
        help="Segundos de espera antes de cerrar el navegador.",
    )


@pytest.fixture(autouse=True)
def _require_selenium_flag(request):
    """Evita ejecutar Selenium salvo que se pida explícitamente."""
    if not request.config.getoption("--selenium"):
        pytest.skip("Usa --selenium para ejecutar los tests de navegador.")


def _free_port() -> int:
    """Reserva un puerto local libre para el servidor Flask."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


class _ServerThread(threading.Thread):
    """Ejecuta Werkzeug en un hilo controlado por pytest."""

    def __init__(self, app, port: int):
        """Inicializa el servidor local de pruebas."""
        super().__init__(daemon=True)
        self.port = port
        self.base_url = f"http://{HOST}:{port}"
        self.server = make_server(HOST, port, app, threaded=True)

    def run(self) -> None:
        """Atiende peticiones HTTP hasta que el fixture lo detenga."""
        self.server.serve_forever()

    def stop(self) -> None:
        """Detiene el servidor local de pruebas."""
        self.server.shutdown()
        self.server.server_close()


def _wait_until_ready(base_url: str) -> None:
    """Espera a que el servidor acepte peticiones HTTP."""
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            urllib.request.urlopen(base_url, timeout=0.2).close()
            return
        except (OSError, urllib.error.URLError):
            time.sleep(0.05)
    raise RuntimeError("El servidor Flask de Selenium no arrancó a tiempo.")


@pytest.fixture
def live_server(app):
    """Levanta la app Flask real en un puerto local temporal."""
    server = _ServerThread(app, _free_port())
    server.start()
    _wait_until_ready(server.base_url)
    yield server.base_url
    server.stop()
    server.join(timeout=3)

    with app.app_context():
        from trazasytrazadas.db import db

        db.session.remove()
        db.engine.dispose()


def _option_float(config, name: str, default: float = 0.0) -> float:
    """Convierte una opción numérica de pytest a float segura."""
    raw_value = config.getoption(name)
    try:
        return max(default, float(raw_value))
    except (TypeError, ValueError):
        return default


def _option_int(config, name: str, default: int = 0) -> int:
    """Convierte una opción numérica de pytest a entero seguro."""
    raw_value = config.getoption(name)
    try:
        return max(default, int(raw_value))
    except (TypeError, ValueError):
        return default


def _apply_slow_motion(driver, delay_seconds: float) -> None:
    """Añade una pausa tras cada comando WebDriver si se configura."""
    if delay_seconds <= 0:
        return

    original_execute = driver.execute

    def slowed_execute(self, command, params=None):
        """Ejecuta un comando WebDriver y espera para verlo en pantalla."""
        result = original_execute(command, params)
        time.sleep(delay_seconds)
        return result

    driver.execute = MethodType(slowed_execute, driver)


def _browser_binary(config) -> str | None:
    """Localiza un binario de Chrome o Chromium disponible."""
    configured = config.getoption("--selenium-browser-binary")
    if configured:
        return configured

    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _driver_path() -> str | None:
    """Devuelve chromedriver si está instalado localmente."""
    configured = os.environ.get("CHROMEDRIVER", "").strip()
    if configured:
        return configured
    return shutil.which("chromedriver")


@pytest.fixture
def browser(request, tmp_path, live_server):
    """Crea un WebDriver Chrome y lo cierra al terminar."""
    pytest.importorskip("selenium")
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service

    options = webdriver.ChromeOptions()

    binary = _browser_binary(request.config)
    if binary:
        options.binary_location = binary

    if not request.config.getoption("--selenium-headed"):
        options.add_argument("--headless=new")

    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--lang=es")

    download_dir = tmp_path / "selenium_downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )

    driver_path = _driver_path()
    allow_manager = os.environ.get("SELENIUM_USE_MANAGER", "1") == "1"

    if driver_path:
        service = Service(executable_path=driver_path)
    elif allow_manager:
        service = Service()
    else:
        pytest.skip(
            "No se encontró chromedriver. Instálalo o usa "
            "SELENIUM_USE_MANAGER=1 si Selenium Manager funciona en "
            "tu entorno."
        )

    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as exc:
        pytest.skip(f"No se pudo iniciar Chrome/Chromium: {exc}")

    slow_ms = _option_int(request.config, "--selenium-slow-ms")
    final_wait = _option_float(request.config, "--selenium-final-wait")
    _apply_slow_motion(driver, slow_ms / 1000)

    driver.selenium_download_dir = download_dir
    driver.set_page_load_timeout(15)
    driver.implicitly_wait(0)
    yield driver

    if final_wait > 0:
        time.sleep(final_wait)

    try:
        driver.get("about:blank")
    finally:
        driver.quit()
