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
from typing import List, Tuple, Dict, Optional

import numpy as np
from PIL import Image

import torch
import segmentation_models_pytorch as smp

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

# ---------------------------
# Carga de modelos por fold
# ---------------------------

def _build_fold_paths(models_dir: str, template: str, n_folds: int) -> List[str]:
    """
    Construye la ruta de fichero para cada fold usando template.
    El template debe contener {fold}.
    """
    paths = []
    for fold in range(n_folds):
        fname = template.format(fold=fold)
        paths.append(os.path.join(models_dir, fname))
    return paths


def _create_unet_model(encoder_name: str) -> torch.nn.Module:
    """
    Crea el U-Net con el encoder.
    classes=1 => segmentación binaria.
    """
    model = smp.create_model(
        "Unet",
        encoder_name=encoder_name,
        in_channels=3,
        classes=1,
    )
    model.eval()
    return model

def _get_preprocess_mean_std(encoder_name: str) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Mean/std del encoder (SMP) para normalizar igual que se entrenó.
    """
    params = smp.encoders.get_preprocessing_params(encoder_name)
    mean = torch.tensor(params["mean"], dtype=torch.float32).view(1, 3, 1, 1)
    std = torch.tensor(params["std"], dtype=torch.float32).view(1, 3, 1, 1)
    return mean, std

@lru_cache(maxsize=1)
def load_fold_models_from_config(
    models_dir: str,
    model_template: str,
    n_folds: int,
    encoder_name: str,
    use_gpu: bool,
) -> Tuple[List[torch.nn.Module], torch.device, torch.Tensor, torch.Tensor]:
    """
    Carga y deja listos los modelos, usando uno por fold, y los mueve al dispositivo.

    IMPORTANTE:
    - Espera pesos en formato state_dict (torch.save(model.state_dict(), path)).
    - Si falta algún fold, lo ignora, pero si no hay ninguno, lanza error.
    """
    device = torch.device("cuda" if (use_gpu and torch.cuda.is_available()) else "cpu")

    mean, std = _get_preprocess_mean_std(encoder_name)
    mean = mean.to(device)
    std = std.to(device)

    fold_paths = _build_fold_paths(models_dir, model_template, n_folds)

    models: List[torch.nn.Module] = []
    missing = []

    for p in fold_paths:
        if not os.path.exists(p):
            missing.append(p)
            continue

        model = _create_unet_model(encoder_name).to(device)
        state = torch.load(p, map_location=device)
        model.load_state_dict(state)
        model.eval()
        models.append(model)

    if not models:
        raise FileNotFoundError(
            "No se encontró ningún modelo de segmentación. "
            f"Busqué en: {models_dir} usando template: {model_template}. "
            f"Ejemplos esperados: {fold_paths[:2]}"
        )

    return models, device, mean, std

# ---------------------------
# Inferencia + ensemble
# ---------------------------

def predict_mask_ensemble(
    image_path: str,
    models_dir: str,
    model_template: str,
    n_folds: int,
    encoder_name: str,
    use_gpu: bool,
    threshold: float = 0.5,
) -> np.ndarray:
    """
    Devuelve máscara binaria final (H,W) sobre el tamaño ORIGINAL de la imagen.

    Proceso:
      - PIL -> tensor
      - padding a múltiplo de 32
      - normalización mean/std encoder
      - predicción por fold (probabilidades)
      - promedio probs
      - threshold -> máscara 0/1
      - recorte a tamaño original
    """
    pil = Image.open(image_path)
    w0, h0 = pil.size

    img_t = _pil_to_tensor_rgb(pil)  # 1,3,H,W (H=h0, W=w0)
    img_t, pad_h, pad_w = _pad_to_multiple_of_32(img_t)

    models, device, mean, std = load_fold_models_from_config(
        models_dir=models_dir,
        model_template=model_template,
        n_folds=n_folds,
        encoder_name=encoder_name,
        use_gpu=use_gpu,
    )

    img_t = img_t.to(device)
    img_t = (img_t - mean) / std

    probs_sum = None

    with torch.no_grad():
        for m in models:
            logits = m(img_t)            # 1,1,Hpad,Wpad
            probs = torch.sigmoid(logits)  # prob [0..1]
            if probs_sum is None:
                probs_sum = probs
            else:
                probs_sum = probs_sum + probs

    probs_avg = probs_sum / float(len(models))
    mask = (probs_avg > threshold).float()  # 1,1,Hpad,Wpad

    mask_np = mask.squeeze().detach().cpu().numpy()  # Hpad,Wpad

    # Recortar padding para volver al tamaño original
    mask_np = mask_np[:h0, :w0]

    return mask_np.astype(np.uint8)

# ---------------------------
# Máscara -> trazas (xs,ys)
# ---------------------------

def mask_to_traces_points(
    mask: np.ndarray,
    max_points: int = 150_000,
    stride: int = 2,
) -> Dict[str, List[int]]:
    """
    Convierte máscara binaria (H,W) en listas xs/ys.
    Para evitar JSON gigantes:
      - stride: muestrea cada N píxeles
      - max_points: límite duro
    """
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
    encoder_name: str,
    use_gpu: bool,
) -> Dict[str, List[int]]:
    """
    Función “puente” a la que llama la app desde /calculate.
    """
    mask = predict_mask_ensemble(
        image_path=image_path,
        models_dir=models_dir,
        model_template=model_template,
        n_folds=n_folds,
        encoder_name=encoder_name,
        use_gpu=use_gpu,
        threshold=0.5,
    )
    return mask_to_traces_points(mask, max_points=150_000, stride=2)