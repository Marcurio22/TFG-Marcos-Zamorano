/**** 
 * GEE Code Editor / Earth Engine App
 * Selector por 2 puntos con drawingTools reales + descargas por imagen.
 *
 * Uso:
 * 1) Pulsa "Añadir punto" y haz 1 clic en el mapa. Repite hasta tener 2 puntos.
 * 2) Pulsa "Crear AOI" para construir el rectángulo entre los dos últimos puntos.
 * 3) Ajusta fechas, nube, dataset, escala y máximo de imágenes.
 * 4) Pulsa "Generar enlaces". Se crearán enlaces de descarga GeoTIFF.
 *
 * Nota: getDownloadURL está pensado para recortes pequeños.
 *       Si el rectángulo es muy grande, algunos enlaces pueden fallar.
 ****/

Map.setOptions('SATELLITE');
Map.setCenter(-3.7038, 40.4168, 6);
Map.setControlVisibility({
  drawingToolsControl: true,
  layerList: true,
  zoomControl: true,
  mapTypeControl: true
});

var drawingTools = Map.drawingTools();
drawingTools.setShown(true);
drawingTools.setLinked(false);

var aoi = null;
var aoiBounds = null;
var aoiLayer = null;
var previewLayer = null;

function clearDrawings() {
  drawingTools.layers().reset([]);
}

function clearAoiPreview() {
  if (aoiLayer) {
    Map.layers().remove(aoiLayer);
    aoiLayer = null;
  }
  aoi = null;
  aoiBounds = null;
}

function clearImagePreview() {
  if (previewLayer) {
    Map.layers().remove(previewLayer);
    previewLayer = null;
  }
}

function resetAll() {
  clearDrawings();
  clearAoiPreview();
  clearImagePreview();
  resultsPanel.clear();
  resultsPanel.add(ui.Label('Aquí aparecerán los enlaces de descarga.'));
  statusLabel.setValue('Listo. Añade dos puntos.');
  pointCountLabel.setValue('Puntos dibujados: 0');
}

function padLeft(value, length, ch) {
  var s = String(value);
  var pad = (ch === undefined) ? '0' : String(ch);
  while (s.length < length) {
    s = pad + s;
  }
  return s;
}

function enterPointMode() {
  drawingTools.setShape('point');
  drawingTools.draw();
  statusLabel.setValue('Modo punto activo: haz 1 clic en el mapa.');
}

function getPointCoords() {
  var pts = [];
  var layers = drawingTools.layers();
  var layerCount = layers.length();

  for (var i = 0; i < layerCount; i++) {
    var layer = layers.get(i);
    var geoms = layer.geometries();
    var geomCount = geoms.length();

    for (var j = 0; j < geomCount; j++) {
      var geom = geoms.get(j);
      try {
        var coords = geom.coordinates().getInfo();
        if (coords && coords.length === 2) {
          pts.push(coords);
        }
      } catch (err) {
        // Ignorar geometrías no compatibles
      }
    }
  }
  return pts;
}

function refreshPointCount() {
  pointCountLabel.setValue('Puntos dibujados: ' + getPointCoords().length);
}

function buildAoiFromPoints() {
  var pts = getPointCoords();
  refreshPointCount();

  if (pts.length < 2) {
    statusLabel.setValue('Necesitas al menos 2 puntos. Usa "Añadir punto" y haz 2 clics.');
    return;
  }

  if (pts.length > 2) {
    statusLabel.setValue('Hay más de 2 puntos: se usarán los dos últimos.');
  } else {
    statusLabel.setValue('AOI creada a partir de 2 puntos.');
  }

  var p1 = pts[pts.length - 2];
  var p2 = pts[pts.length - 1];

  var lonMin = Math.min(p1[0], p2[0]);
  var lonMax = Math.max(p1[0], p2[0]);
  var latMin = Math.min(p1[1], p2[1]);
  var latMax = Math.max(p1[1], p2[1]);

  if (lonMin === lonMax || latMin === latMax) {
    statusLabel.setValue('Los dos puntos no pueden compartir exactamente la misma longitud o latitud.');
    return;
  }

  clearAoiPreview();

  aoiBounds = {
    lonMin: lonMin,
    latMin: latMin,
    lonMax: lonMax,
    latMax: latMax
  };

  aoi = ee.Geometry.Rectangle([lonMin, latMin, lonMax, latMax], null, false);
  aoiLayer = ui.Map.Layer(
    ee.FeatureCollection([ee.Feature(aoi)]),
    {color: 'yellow'},
    'AOI'
  );

  Map.layers().add(aoiLayer);
  Map.centerObject(aoi, 13);
}

function getDatasetSpec() {
  var dataset = datasetSelect.getValue();

  if (dataset === 'S2') {
    return {
      label: 'Sentinel-2 SR Harmonized',
      collection: ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(aoi)
        .filterDate(startDateBox.getValue(), endDateBox.getValue())
        .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', parseFloat(cloudBox.getValue()) || 20))
        .sort('system:time_start'),
      prepare: function(img) {
        return ee.Image(img).select(['B4', 'B3', 'B2']).clip(aoi);
      },
      vis: {min: 0, max: 3000, bands: ['B4', 'B3', 'B2']},
      recommendedScale: 10,
      prefix: 'S2'
    };
  }

  if (dataset === 'PNOA10') {
    return {
      label: 'Spain PNOA10',
      collection: ee.ImageCollection('Spain/PNOA/PNOA10')
        .filterBounds(aoi)
        .filterDate(startDateBox.getValue(), endDateBox.getValue())
        .sort('system:time_start'),
      prepare: function(img) {
        return ee.Image(img).select(['R', 'G', 'B']).clip(aoi);
      },
      vis: {min: 0, max: 255, bands: ['R', 'G', 'B']},
      recommendedScale: 0.1,
      prefix: 'PNOA10'
    };
  }

  throw new Error('Dataset no soportado: ' + dataset);
}

function formatMillis(ms) {
  var d = new Date(ms);
  var y = d.getUTCFullYear();
  var m = padLeft(d.getUTCMonth() + 1, 2, '0');
  var day = padLeft(d.getUTCDate(), 2, '0');
  return y + '-' + m + '-' + day;
}

function safeName(text, fallback) {
  var t = String(text || fallback || 'img');
  return t.replace(/[^A-Za-z0-9_\\-]+/g, '_');
}

function estimateBboxInfo(bounds) {
  var widthDeg = Math.abs(bounds[2] - bounds[0]);
  var heightDeg = Math.abs(bounds[3] - bounds[1]);
  return 'BBox lon/lat ≈ ' + widthDeg.toFixed(6) + ' × ' + heightDeg.toFixed(6) + ' grados';
}

function generateLinks() {
  resultsPanel.clear();
  clearImagePreview();

  if (!aoi) {
    statusLabel.setValue('Primero crea el AOI con dos puntos.');
    resultsPanel.add(ui.Label('Primero crea el AOI.'));
    return;
  }

  if (!aoiBounds) {
    statusLabel.setValue('No hay bbox disponible. Vuelve a crear el AOI.');
    resultsPanel.add(ui.Label('No hay bbox disponible.'));
    return;
  }

  var maxImages = parseInt(maxImagesBox.getValue(), 10);
  if (!maxImages || maxImages < 1) {
    maxImages = 10;
    maxImagesBox.setValue(String(maxImages));
  }

  var requestedScale = parseFloat(scaleBox.getValue());
  if (!requestedScale || requestedScale <= 0) {
    requestedScale = 10;
    scaleBox.setValue(String(requestedScale));
  }

  var lonMin = aoiBounds.lonMin;
  var latMin = aoiBounds.latMin;
  var lonMax = aoiBounds.lonMax;
  var latMax = aoiBounds.latMax;

  resultsPanel.add(ui.Label(estimateBboxInfo([lonMin, latMin, lonMax, latMax])));

  var spec = getDatasetSpec();
  statusLabel.setValue('Consultando colección: ' + spec.label + ' ...');
  resultsPanel.add(ui.Label('Buscando en: ' + spec.label));
  resultsPanel.add(
    ui.Label(
      'Escala solicitada: ' + requestedScale +
      ' m/px (recomendada para este dataset: ' + spec.recommendedScale + ' m/px)'
    )
  );

  var limited = spec.collection.limit(maxImages);
  var size = limited.size();

  size.evaluate(function(count) {
    if (!count || count === 0) {
      statusLabel.setValue('No se encontraron imágenes para ese AOI y filtros.');
      resultsPanel.add(ui.Label('No se encontraron imágenes. Revisa fechas, nube o dataset.'));
      return;
    }

    statusLabel.setValue('Imágenes encontradas: ' + count + '. Generando enlaces...');
    resultsPanel.add(ui.Label('Imágenes encontradas: ' + count, {fontWeight: 'bold'}));

    var ids = limited.aggregate_array('system:index');
    var times = limited.aggregate_array('system:time_start');

    ee.Dictionary({ids: ids, times: times}).evaluate(function(meta) {
      var idList = (meta && meta.ids) ? meta.ids : [];
      var timeList = (meta && meta.times) ? meta.times : [];
      var imgList = limited.toList(count);

      for (var i = 0; i < count; i++) {
        var img = ee.Image(imgList.get(i));
        var id = idList[i] || ('img_' + (i + 1));
        var millis = timeList[i] || 0;
        var dateStr = millis ? formatMillis(millis) : 'sin_fecha';
        var prepared = spec.prepare(img);

        if (i === 0) {
          previewLayer = ui.Map.Layer(prepared, spec.vis, 'Vista previa (1ª imagen)');
          Map.layers().add(previewLayer);
        }

        prepared.getDownloadURL({
          region: aoi,
          scale: requestedScale,
          format: 'GEO_TIFF',
          filePerBand: false,
          name: safeName(spec.prefix + '_' + dateStr + '_' + id, 'download_' + (i + 1))
        }, (function(iCopy, dateCopy, idCopy) {
          return function(url, err) {
            if (err || !url) {
              resultsPanel.add(ui.Label(
                (iCopy + 1) + '. ' + dateCopy + ' | ' + idCopy +
                ' → No se pudo generar la URL.',
                {color: 'red'}
              ));
              return;
            }

            var row = ui.Panel(
              [
                ui.Label((iCopy + 1) + '. ' + dateCopy + ' | ' + idCopy, {
                  fontWeight: 'bold'
                }),
                ui.Label({
                  value: 'Descargar GeoTIFF',
                  targetUrl: url,
                  style: {
                    color: '#1a73e8',
                    textDecoration: 'underline',
                    margin: '2px 0 0 12px'
                  }
                })
              ],
              ui.Panel.Layout.flow('vertical'),
              {
                margin: '0 0 8px 0',
                padding: '6px',
                border: '1px solid #d9d9d9',
                backgroundColor: '#fafafa'
              }
            );

            resultsPanel.add(row);
          };
        })(i, dateStr, id));
      }

      statusLabel.setValue('Listo. Se han solicitado ' + count + ' enlace(s).');
    });
  });
}

// Panel lateral
var title = ui.Label('Descarga de imágenes por AOI (2 puntos)', {
  fontWeight: 'bold',
  fontSize: '18px',
  margin: '0 0 8px 0'
});

var help = ui.Label(
  'Usa los drawing tools reales del mapa para colocar 2 puntos. El script crea el rectángulo entre esos puntos y genera un enlace de descarga GeoTIFF por cada imagen que intersecta el AOI.',
  {whiteSpace: 'wrap', margin: '0 0 10px 0'}
);

var note = ui.Label(
  'Consejo: para AOIs grandes o escalas muy finas, getDownloadURL puede fallar. Mantén recortes pequeños.',
  {whiteSpace: 'wrap', color: '#a15c00', margin: '0 0 10px 0'}
);

var addPointButton = ui.Button(
  '1) Añadir punto (haz 1 clic)',
  enterPointMode,
  false,
  {stretch: 'horizontal'}
);

var buildAoiButton = ui.Button(
  '2) Crear AOI con los 2 últimos puntos',
  buildAoiFromPoints,
  false,
  {stretch: 'horizontal'}
);

var clearButton = ui.Button(
  'Limpiar todo',
  resetAll,
  false,
  {stretch: 'horizontal'}
);

var datasetSelect = ui.Select({
  items: [
    {label: 'Sentinel-2 SR (RGB)', value: 'S2'},
    {label: 'Spain PNOA10 (RGB)', value: 'PNOA10'}
  ],
  value: 'S2',
  style: {stretch: 'horizontal'}
});

var startDateBox = ui.Textbox({
  placeholder: 'YYYY-MM-DD',
  value: '2025-01-01',
  style: {stretch: 'horizontal'}
});

var endDateBox = ui.Textbox({
  placeholder: 'YYYY-MM-DD',
  value: '2025-12-31',
  style: {stretch: 'horizontal'}
});

var cloudBox = ui.Textbox({
  placeholder: '20',
  value: '20',
  style: {stretch: 'horizontal'}
});

var scaleBox = ui.Textbox({
  placeholder: '10',
  value: '10',
  style: {stretch: 'horizontal'}
});

var maxImagesBox = ui.Textbox({
  placeholder: '10',
  value: '10',
  style: {stretch: 'horizontal'}
});

var generateButton = ui.Button(
  '3) Generar enlaces de descarga',
  generateLinks,
  false,
  {
    stretch: 'horizontal',
    color: 'white',
    backgroundColor: '#1a73e8'
  }
);

var pointCountLabel = ui.Label('Puntos dibujados: 0', {margin: '8px 0 4px 0'});

var statusLabel = ui.Label('Listo. Añade dos puntos.', {
  margin: '8px 0 8px 0',
  color: '#0b8043',
  whiteSpace: 'wrap'
});

var resultsTitle = ui.Label('Resultados', {
  fontWeight: 'bold',
  margin: '12px 0 6px 0'
});

var resultsPanel = ui.Panel(
  [ui.Label('Aquí aparecerán los enlaces de descarga.')],
  null,
  {
    stretch: 'both',
    height: '360px',
    shown: true
  }
);

var controls = ui.Panel({
  widgets: [
    title,
    help,
    note,
    addPointButton,
    buildAoiButton,
    clearButton,
    pointCountLabel,
    ui.Label('Dataset'),
    datasetSelect,
    ui.Label('Fecha inicio'),
    startDateBox,
    ui.Label('Fecha fin'),
    endDateBox,
    ui.Label('Nubosidad máxima (%) — solo Sentinel-2'),
    cloudBox,
    ui.Label('Escala de descarga (m/px)'),
    scaleBox,
    ui.Label('Máximo de imágenes'),
    maxImagesBox,
    generateButton,
    statusLabel,
    resultsTitle,
    resultsPanel
  ],
  style: {
    width: '430px',
    padding: '8px'
  }
});

// Evitar duplicar panel si re-ejecutas el script
if (ui.root.widgets().length() > 1) {
  ui.root.remove(ui.root.widgets().get(0));
}

// Mantener el mapa por defecto del Code Editor y poner los controles a la izquierda.
ui.root.insert(0, controls);

// Actualizar contador cuando cambien las capas de dibujo
drawingTools.onLayerAdd(refreshPointCount);
drawingTools.onLayerRemove(refreshPointCount);

// Estado inicial
resetAll();