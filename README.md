<a name="readme-top"></a>

<div align="center">

# Trazas y Trazadas

### Aplicación web para el análisis de trazas de herbívoros sobre imágenes y zonas cartográficas

![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Web%20app-000000?style=for-the-badge&logo=flask&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Jinja](https://img.shields.io/badge/Jinja2-Templates-B41717?style=for-the-badge&logo=jinja&logoColor=white)

![Tailwind CSS](https://img.shields.io/badge/Tailwind%20CSS-UI-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white)
![DaisyUI](https://img.shields.io/badge/DaisyUI-Components-5A0EF8?style=for-the-badge)
![JavaScript](https://img.shields.io/badge/JavaScript-Vanilla-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)
![pytest](https://img.shields.io/badge/pytest-Tests-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)
![Selenium](https://img.shields.io/badge/Selenium-E2E-43B02A?style=for-the-badge&logo=selenium&logoColor=white)

<br />

**Trabajo Fin de Grado — Marcos Zamorano Lasso**

Aplicación Flask monolítica modularizada para subir imágenes, calcular trazas,
trabajar con visor cartográfico, generar colecciones de teselas y administrar
usuarios y modelos de segmentación.

</div>

---

## Contenido

- [Descripción](#descripción)
- [Características principales](#características-principales)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Tecnologías](#tecnologías)
- [Instalación](#instalación)
- [Ejecución de la aplicación](#ejecución-de-la-aplicación)
- [Usuarios de demostración](#usuarios-de-demostración)
- [Pruebas](#pruebas)
- [Internacionalización](#internacionalización)
- [Notas para desarrollo](#notas-para-desarrollo)
- [Autor](#autor)

---

## Descripción

**Trazas y Trazadas** es una aplicación web desarrollada como parte de un
Trabajo Fin de Grado. Su objetivo es facilitar el análisis de trazas de
herbívoros a partir de imágenes individuales y zonas cartográficas.

El sistema permite cargar imágenes, ejecutar inferencia de segmentación,
generar resultados descargables, seleccionar áreas en un visor cartográfico,
dividirlas en teselas, almacenar colecciones y consultar el estado de
procesamiento de cada zona.

La aplicación también incluye autenticación, perfil de usuario, imagen de
perfil, administración de usuarios, gestión de modelos de segmentación,
internacionalización y una suite amplia de pruebas automáticas.

<p align="right">(<a href="#readme-top">volver al principio</a>)</p>

---

## Características principales

- Subida de imágenes individuales y cálculo de trazas.
- Visualización de resultados y descarga de archivos generados.
- Visor cartográfico con selección de zona y generación de cuadrículas.
- Colección persistente de zonas, teselas y resultados asociados.
- Galería de teselas con visualización de trazas.
- Pausa y reanudación del procesamiento de trazas por colección.
- Registro, login, logout, perfil e imagen de usuario.
- Panel de administración de usuarios.
- Gestión administrativa de modelos de segmentación.
- Worker interno para procesar teselas pendientes.
- Interfaz construida con Jinja2, Tailwind CSS y DaisyUI.
- Internacionalización con Flask-Babel.
- Tests con pytest, coverage y Selenium.

<p align="right">(<a href="#readme-top">volver al principio</a>)</p>

---

## Estructura del repositorio

La raíz del repositorio contiene la documentación, prototipos, pruebas y la
aplicación web principal.

```text
/
├── assets/              Recursos gráficos y materiales auxiliares.
├── doc/                 Documentación técnica y memoria del TFG.
├── htmlcov/             Informe HTML de cobertura generado por coverage.
├── prototipos/          Pruebas preliminares realizadas durante el desarrollo.
├── tests/               Suite de pruebas automáticas del sistema.
│   └── selenium/        Tests funcionales ejecutados en navegador real.
└── webapp/              Aplicación web Flask.
    ├── instance/        Recursos locales y base de datos SQLite.
    ├── scripts/         Scripts auxiliares de mantenimiento.
    └── trazasytrazadas/ Paquete principal de la aplicación.
        ├── static/      Ficheros estáticos: imágenes, CSS y JavaScript.
        └── templates/   Plantillas HTML Jinja2.
```

Dentro de `webapp/trazasytrazadas` se encuentra el núcleo de la aplicación:
factoría Flask, rutas, modelos, formularios, visor, colección, administración,
inferencia y worker de trazas.

<p align="right">(<a href="#readme-top">volver al principio</a>)</p>

---

## Tecnologías

El proyecto utiliza principalmente:

- **Python** como lenguaje principal.
- **Flask** como framework web.
- **Flask-Login** para autenticación.
- **Flask-Babel** para internacionalización.
- **Flask-WTF / WTForms** para formularios.
- **SQLAlchemy** como ORM.
- **SQLite** como base de datos local.
- **Jinja2** para plantillas HTML.
- **Tailwind CSS** y **DaisyUI** para interfaz.
- **JavaScript vanilla** para interacción en cliente.
- **pytest** para pruebas automáticas.
- **coverage / pytest-cov** para medición de cobertura.
- **Selenium** para pruebas funcionales en navegador.
- **Git** para control de versiones.

<p align="right">(<a href="#readme-top">volver al principio</a>)</p>

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd TFG-Marcos-Zamorano
```

### 2. Crear y activar un entorno virtual

En Windows PowerShell:

```powershell
python -m venv TFG_env
.\TFG_env\Scripts\Activate.ps1
```

En Linux/macOS:

```bash
python -m venv TFG_env
source TFG_env/bin/activate
```

### 3. Instalar dependencias principales

```bash
pip install -r webapp/requirements.txt
```

## Ejecución de la aplicación

Desde la raíz del repositorio:

```bash
cd webapp
flask --app run run
```

También puede ejecutarse con:

```bash
cd webapp
python run.py
```

La aplicación quedará disponible normalmente en:

```text
http://127.0.0.1:5000
```

<p align="right">(<a href="#readme-top">volver al principio</a>)</p>

---

## Usuarios de demostración

La carga inicial del sistema incluye usuarios de demostración. Estas cuentas
están pensadas para pruebas locales y revisión académica. En un entorno real
de despliegue deberían cambiarse o eliminarse.

| Usuario | Rol | Contraseña |
|---|---:|---|
| `MarcosZ` | Administrador | `Administrador.22` |
| `Vindi222` | Administrador | `Administrador.11` |
| `JavierGarcia` | Usuario | `JuanjoElMejor2@` |
| `Nickyer.25` | Usuario | `Usuario.1` |
| `MCasadó` | Usuario | `Usuario.2` |

<p align="right">(<a href="#readme-top">volver al principio</a>)</p>

---

## Pruebas

La suite de pruebas se encuentra en el directorio `tests/`, situado en la raíz
del repositorio.

### Tests funcionales y de regresión

```bash
pytest -q
```

### Coverage

```bash
pytest --cov=trazasytrazadas --cov-report=term-missing
```

Para generar también informe HTML y XML:

```bash
pytest --cov=trazasytrazadas \
  --cov-report=term-missing \
  --cov-report=html \
  --cov-report=xml
```

El informe HTML se genera en:

```text
htmlcov/index.html
```

### Tests Selenium

Los tests Selenium validan flujos reales de navegador:

```bash
pytest tests/selenium --selenium -q
```

Para ver el navegador durante la ejecución:

```bash
pytest tests/selenium --selenium --selenium-headed -q
```

Para ralentizar la ejecución y poder observar los pasos:

```bash
pytest tests/selenium --selenium --selenium-headed \
  --selenium-slow-ms=350 -q
```

<p align="right">(<a href="#readme-top">volver al principio</a>)</p>

---

## Internacionalización

La aplicación utiliza **Flask-Babel**. El idioma base de los `msgid` es el
español y la plantilla principal de traducciones se encuentra en
`messages.pot`.

Los textos visibles para el usuario deben envolverse con `_()` en Python y
Jinja. Para JavaScript estático, no debe introducirse Jinja directamente en los
ficheros `.js`; los textos y datos dinámicos se inyectan desde las plantillas
mediante objetos globales como:

- `window.TRACES_APP`
- `window.VISOR_APP`
- `window.COLLECTION_APP`

<p align="right">(<a href="#readme-top">volver al principio</a>)</p>

---

## Notas para desarrollo

- Mantener la arquitectura Flask existente con Application Factory y blueprints.
- Evitar reescrituras generales si no son necesarias.
- Añadir o actualizar tests antes de modificar funcionalidades delicadas.
- Mantener separados los cambios funcionales, visuales, de tests e i18n.
- No introducir Jinja directamente en ficheros JavaScript estáticos.
- Respetar permisos, roles y propiedad de recursos de usuario.
- Revisar con especial cuidado cambios en modelos, colección, worker,
  imágenes de perfil e inferencia.
- No versionar artefactos generados localmente, bases de datos, cachés ni
  resultados temporales.

<p align="right">(<a href="#readme-top">volver al principio</a>)</p>

---

## Autor

**Marcos Zamorano Lasso**

Trabajo Fin de Grado — Aplicación web para análisis de trazas de herbívoros.

<p align="right">(<a href="#readme-top">volver al principio</a>)</p>
