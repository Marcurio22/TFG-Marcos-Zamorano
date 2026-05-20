"""
==============================================================================
Fixtures de Selenium para pruebas funcionales de navegador.

Levanta la aplicación Flask en un puerto local y crea un navegador Chrome en
modo headless para ejecutar flujos reales de usuario.

Autor: Marcos Zamorano Lasso
Versión: 0.1
==============================================================================
"""

from __future__ import annotations

import os
import shutil
import socket
import threading
import time
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
def browser(request):
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

    driver_path = _driver_path()
    allow_manager = os.environ.get("SELENIUM_USE_MANAGER", "1") == "1"

    if driver_path:
        service = Service(executable_path=driver_path)
    elif allow_manager:
        service = Service()
    else:
        pytest.skip(
            "No se encontró chromedriver."
        )

    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as exc:
        pytest.skip(f"No se pudo iniciar Chrome/Chromium: {exc}")

    driver.set_page_load_timeout(15)
    driver.implicitly_wait(0)
    yield driver
    driver.quit()
