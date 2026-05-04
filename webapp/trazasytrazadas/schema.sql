-- ============================================================================
-- Esquema SQLite para la colección de imágenes.
--
-- Autor: Marcos Zamorano Lasso
-- Versión: 0.1
-- ============================================================================

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS usuario (
    usuario_id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_usuario VARCHAR(50) NOT NULL UNIQUE,
    contrasena VARCHAR(255) NOT NULL,
    correo_electronico VARCHAR(50) NOT NULL UNIQUE,
    telefono VARCHAR(20),
    ruta_imagen_perfil TEXT,
    rol VARCHAR(20) NOT NULL CHECK (rol IN ('system', 'admin', 'user')),
    fecha_alta TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS parcela (
    parcela_id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    tamano_metros REAL NOT NULL,
    pto_origen_lat REAL NOT NULL,
    pto_origen_lng REAL NOT NULL,
    pto_fin_lat REAL NOT NULL,
    pto_fin_lng REAL NOT NULL,
    fecha TEXT NOT NULL DEFAULT (DATE('now')),
    bbox_json TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_label TEXT NOT NULL,
    requested_resolution REAL NOT NULL,
    actual_resolution REAL NOT NULL,
    tile_width INTEGER NOT NULL,
    tile_height INTEGER NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pending'
        CHECK (estado IN ('pending', 'processing', 'completed', 'failed')),
    nombre_coleccion TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuario (usuario_id)
);

CREATE TABLE IF NOT EXISTS foto (
    foto_id INTEGER PRIMARY KEY AUTOINCREMENT,
    parcela_id INTEGER NOT NULL,
    fecha_foto TEXT NOT NULL,
    resolucion_valor REAL NOT NULL,
    resolucion_unidad TEXT NOT NULL,
    longitud REAL NOT NULL,
    latitud REAL NOT NULL,
    ruta_foto TEXT NOT NULL,
    ruta_trazas TEXT,
    trazas INTEGER NOT NULL DEFAULT 0 CHECK (trazas IN (0, 1)),
    estado TEXT NOT NULL DEFAULT 'pending'
        CHECK (estado IN ('pending', 'processing', 'completed', 'failed')),
    error_message TEXT,
    started_at TEXT,
    finished_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    tile_id TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    col_index INTEGER NOT NULL,
    filename TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    bbox3857_json TEXT NOT NULL,
    bounds_json TEXT NOT NULL,
    source_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parcela_id) REFERENCES parcela (parcela_id) ON DELETE CASCADE,
    UNIQUE (parcela_id, tile_id)
);

CREATE INDEX IF NOT EXISTS idx_parcela_usuario_fecha
    ON parcela (usuario_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_foto_parcela
    ON foto (parcela_id, row_index, col_index);

INSERT OR IGNORE INTO usuario (
    usuario_id,
    nombre_usuario,
    contrasena,
    correo_electronico,
    rol
)
VALUES (
    1,
    'system',
    'disabled',
    'system@local.invalid',
    'system'
);