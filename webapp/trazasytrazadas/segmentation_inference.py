"""
segmentation_inference.py
-------------------------
Inferencia de segmentación semántica usando U-Net con la biblioteca segmentation_models_pytorch
con múltiples modelos mediante folds y generación de trazas: xs, ys, para el frontend.

Características:
- Padding a múltiplos de 32 (requisito típico U-Net/encoders).
- Ensemble multi-fold: media de probabilidades -> umbral -> máscara final.
- Conversión máscara -> lista de coordenadas (xs, ys), con muestreo para no
  generar JSON gigantes.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Tuple, Dict

import numpy as np
from PIL import Image

import torch

# ---------------------------
# Utilidades de preprocesado
# ---------------------------

def _pad_to_multiple_of_32(img_t: torch.Tensor) -> Tuple[torch.Tensor, int, int]:
    """
    Aplica padding (abajo/derecha) para que H y W sean múltiplos de 32.
    Devuelve el tensor padded y cuánto padding se añadió (pad_h, pad_w).

    img_t: (1, 3, H, W)
    """
    _, _, h, w = img_t.shape
    new_h = int(np.ceil(h / 32) * 32)
    new_w = int(np.ceil(w / 32) * 32)
    pad_h = new_h - h
    pad_w = new_w - w

    if pad_h == 0 and pad_w == 0:
        return img_t, 0, 0

    # Padding formato torch.nn.functional.pad: (left, right, top, bottom)
    img_t = torch.nn.functional.pad(img_t, (0, pad_w, 0, pad_h), mode="constant", value=0.0)
    return img_t, pad_h, pad_w

def _pil_to_tensor_rgb(pil_img: Image.Image) -> torch.Tensor:
    """
    PIL -> Tensor float32 [0,1], shape (1,3,H,W)
    """
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    arr = np.asarray(pil_img).astype(np.float32) / 255.0  # H,W,3
    t = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)  # 1,3,H,W
    return t

def _normalize_imagenet(img_t: torch.Tensor, device: torch.device) -> torch.Tensor:
    """
    Normalización usada en encoders.
    """
    mean = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32, device=device).view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32, device=device).view(1, 3, 1, 1)
    return (img_t - mean) / std

# ---------------------------
# Carga de modelos TorchScript
# ---------------------------

@lru_cache(maxsize=1)
def load_fold_torchscript_models(models_dir: str, model_template: str, n_folds: int, use_gpu: bool):
    device = torch.device("cuda" if (use_gpu and torch.cuda.is_available()) else "cpu")

    models = []
    for fold in range(n_folds):
        p = os.path.join(models_dir, model_template.format(fold=fold))
        if not os.path.exists(p):
            continue
        m = torch.jit.load(p, map_location=device)
        m.eval()
        models.append(m)

    if not models:
        raise FileNotFoundError(
            f"No se encontró ningún modelo TorchScript en {models_dir} con template {model_template}"
        )

    return models, device

# ---------------------------
# Inferencia + ensemble
# ---------------------------

def predict_mask_ensemble(
    image_path: str,
    models_dir: str,
    model_template: str,
    n_folds: int,
    use_gpu: bool,
    threshold: float = 0.5,
) -> np.ndarray:
    pil = Image.open(image_path)
    w0, h0 = pil.size

    img_t = _pil_to_tensor_rgb(pil)
    img_t, _, _ = _pad_to_multiple_of_32(img_t)

    models, device = load_fold_torchscript_models(
        models_dir=models_dir,
        model_template=model_template,
        n_folds=n_folds,
        use_gpu=use_gpu,
    )

    img_t = img_t.to(device)
    # img_t = _normalize_imagenet(img_t, device)

    probs_sum = None

    with torch.no_grad():
        for m in models:
            probs = m(img_t)
            probs_sum = probs if probs_sum is None else (probs_sum + probs)

    probs_avg = probs_sum / float(len(models))
    mask = (probs_avg > threshold).float()

    mask_np = mask.squeeze().detach().cpu().numpy()
    mask_np = mask_np[:h0, :w0]  # recorte a tamaño original

    return mask_np.astype(np.uint8)

# ---------------------------
# Máscara -> trazas (xs,ys)
# ---------------------------

def mask_to_traces_points(
    mask: np.ndarray,
    max_points: int = 150_000,
    stride: int = 2,
) -> Dict[str, List[int]]:
    ys, xs = np.where(mask > 0)

    if xs.size == 0:
        return {"xs": [], "ys": []}

    # Muestreo por stride
    if stride > 1:
        xs = xs[::stride]
        ys = ys[::stride]

    # Límite de puntos
    if xs.size > max_points:
        idx = np.linspace(0, xs.size - 1, max_points).astype(int)
        xs = xs[idx]
        ys = ys[idx]

    return {"xs": xs.astype(int).tolist(), "ys": ys.astype(int).tolist()}


def compute_traces_from_segmentation(
    image_path: str,
    models_dir: str,
    model_template: str,
    n_folds: int,
    use_gpu: bool,
) -> Dict[str, List[int]]:
    """
    Función puente a la que llama la app desde /calculate.
    """
    mask = predict_mask_ensemble(
        image_path=image_path,
        models_dir=models_dir,
        model_template=model_template,
        n_folds=n_folds,
        use_gpu=use_gpu,
        threshold=0.5,
    )
    return mask_to_traces_points(mask, max_points=150_000, stride=2)