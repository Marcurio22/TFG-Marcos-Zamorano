import os
from flask import Flask, request, jsonify, send_from_directory
import ee

GEE_PROJECT = os.environ.get("GEE_PROJECT")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)


def init_ee():
    if GEE_PROJECT:
        ee.Initialize(project=GEE_PROJECT)
    else:
        ee.Initialize()


# Hay que autenticarse antes de arrancar el server.
init_ee()


def parse_date(s: str) -> str:
    if not s or len(s) != 10:
        raise ValueError("Fecha inválida, usa YYYY-MM-DD.")
    return s


def rect_from_points(p1, p2):
    lon_min = min(p1["lng"], p2["lng"])
    lon_max = max(p1["lng"], p2["lng"])
    lat_min = min(p1["lat"], p2["lat"])
    lat_max = max(p1["lat"], p2["lat"])
    if lon_min == lon_max or lat_min == lat_max:
        raise ValueError(
            "Los puntos no pueden tener la misma latitud o longitud.")
    return ee.Geometry.Rectangle([lon_min, lat_min, lon_max, lat_max], None, False)


def build_composite(dataset: str, aoi: ee.Geometry, start: str, end: str, cloud: float):
    if dataset == "S2_MEDIAN":
        col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
               .filterBounds(aoi)
               .filterDate(start, end)
               .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", cloud)))
        img = col.median().select(["B4", "B3", "B2"]).clip(aoi)
        vis = {"min": 0, "max": 3000, "bands": ["B4", "B3", "B2"]}
        return img, vis, 10, "S2_MEDIAN"

    if dataset == "L89_MEDIAN":
        col = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
               .merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
               .filterBounds(aoi)
               .filterDate(start, end)
               .filter(ee.Filter.lte("CLOUD_COVER", cloud)))
        img = col.median().select(["SR_B4", "SR_B3", "SR_B2"]).clip(aoi)
        vis = {"min": 7000, "max": 18000, "bands": ["SR_B4", "SR_B3", "SR_B2"]}
        return img, vis, 30, "L89_MEDIAN"

    raise ValueError(f"Dataset no soportado: {dataset}")


@app.get("/")
def index():
    return send_from_directory(APP_DIR, "gee_aoi_app.html")


@app.post("/api/thumb")
def api_thumb():
    try:
        data = request.get_json(force=True)
        aoi = rect_from_points(data["p1"], data["p2"])
        dataset = data.get("dataset", "S2_MEDIAN")
        start = parse_date(data.get("start", "2024-06-01"))
        end = parse_date(data.get("end", "2024-09-30"))
        cloud = float(data.get("cloud", 20))
        fmt = data.get("thumb_format", "png")
        width = int(data.get("thumb_width", 1024))

        img, vis, _, label = build_composite(dataset, aoi, start, end, cloud)
        params = dict(vis)
        params.update({"region": aoi, "dimensions": width, "format": fmt})
        url = img.getThumbURL(params)
        return jsonify({"url": url, "dataset": label})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/download")
def api_download():
    try:
        data = request.get_json(force=True)
        aoi = rect_from_points(data["p1"], data["p2"])
        dataset = data.get("dataset", "S2_MEDIAN")
        start = parse_date(data.get("start", "2024-06-01"))
        end = parse_date(data.get("end", "2024-09-30"))
        cloud = float(data.get("cloud", 20))
        scale = float(data.get("scale", 10))

        img, _, rec_scale, label = build_composite(
            dataset, aoi, start, end, cloud)
        url = img.getDownloadURL({
            "region": aoi,
            "scale": scale,
            "format": "GEO_TIFF",
            "filePerBand": False,
            "name": f"{label}_{start}_to_{end}"
        })
        return jsonify({"url": url, "recommended_scale": rec_scale, "dataset": label})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/export")
def api_export():
    try:
        data = request.get_json(force=True)
        aoi = rect_from_points(data["p1"], data["p2"])
        dataset = data.get("dataset", "S2_MEDIAN")
        start = parse_date(data.get("start", "2024-06-01"))
        end = parse_date(data.get("end", "2024-09-30"))
        cloud = float(data.get("cloud", 20))
        scale = float(data.get("scale", 10))

        img, _, rec_scale, label = build_composite(
            dataset, aoi, start, end, cloud)

        task = ee.batch.Export.image.toDrive(
            image=img,
            description=f"EXPORT_{label}_{start}_to_{end}",
            folder="GEE_AOI_EXPORTS",
            fileNamePrefix=f"{label}_{start}_to_{end}",
            region=aoi,
            scale=scale,
            maxPixels=1e13
        )
        task.start()
        return jsonify({"task_id": task.id, "recommended_scale": rec_scale, "dataset": label})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="127.0.0.1", port=port, debug=False)
