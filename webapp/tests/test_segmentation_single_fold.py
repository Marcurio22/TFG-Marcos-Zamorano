"""
Prueba del comportamiento de inferencia con un único modelo activo.

Este módulo verifica que la función de predicción carga el modelo activo por
nombre de fichero y que la máscara resultante mantiene el tamaño original de
la imagen.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

import numpy as np
import torch
from PIL import Image

import trazasytrazadas.segmentation_inference as si


class DummyModel(torch.nn.Module):
    """Modelo mínimo que devuelve una máscara completamente positiva."""

    def forward(self, x):
        return torch.ones((1, 1, x.shape[2], x.shape[3]), device=x.device)


def test_predict_uses_active_model_name(tmp_path, monkeypatch):
    """Comprueba que la inferencia solicita el modelo activo por nombre."""
    img_path = tmp_path / "img.jpg"
    Image.new("RGB", (37, 45), color="white").save(img_path)

    called = {"model_name": None, "times": 0}

    # Sustituye el cargador real para capturar el modelo solicitado y evitar
    # dependencias de modelos serializados.
    def fake_loader(models_dir, model_name, use_gpu):
        called["model_name"] = model_name
        called["times"] += 1
        device = torch.device("cpu")
        return [DummyModel().to(device).eval()], device

    monkeypatch.setattr(si, "load_model_file_models", fake_loader)

    mask = si.predict_mask_ensemble(
        image_path=str(img_path),
        models_dir="X",
        model_template="Y",
        use_gpu=False,
        threshold=0.5,
    )

    assert called["times"] == 1
    assert called["model_name"] == "fold.0"
    assert isinstance(mask, np.ndarray)
    assert mask.shape == (45, 37)
    assert mask.dtype == np.uint8
    assert mask.min() == 1 and mask.max() == 1
