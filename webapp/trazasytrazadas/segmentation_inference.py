"""
Inferencia de segmentación y conversión de máscaras a trazas para el frontend.

Este módulo prepara la imagen de entrada, carga el modelo serializado con
pickle, ejecuta la inferencia y transforma la máscara resultante en
coordenadas {xs, ys} consumibles por el frontend.

También incluye compatibilidad con pickles generados en entornos de
entrenamiento anteriores y una carga cacheada del modelo para evitar recargas
innecesarias.

Autor: Marcos Zamorano Lasso
Versión: 0.1
"""

from __future__ import annotations

import os
import sys
import pickle
from functools import lru_cache
from typing import List, Tuple, Dict

import numpy as np
from PIL import Image

import torch
import torch.nn as nn
import torch.nn.functional as F


# Preprocesado de entrada.

def _pad_to_multiple_of_32(
    img_t: torch.Tensor,
) -> Tuple[torch.Tensor, int, int]:
    """
    Ajusta el tensor de entrada a múltiplos de 32 mediante padding al final.

    Returns:
        Tuple[torch.Tensor, int, int]: Tensor ajustado, padding añadido en
        alto y padding añadido en ancho.
    """
    _, _, h, w = img_t.shape
    new_h = int(np.ceil(h / 32) * 32)
    new_w = int(np.ceil(w / 32) * 32)
    pad_h = new_h - h
    pad_w = new_w - w
    if pad_h == 0 and pad_w == 0:
        return img_t, 0, 0
    img_t = F.pad(img_t, (0, pad_w, 0, pad_h), mode="constant", value=0.0)
    return img_t, pad_h, pad_w


def _pil_to_tensor_rgb(pil_img: Image.Image) -> torch.Tensor:
    """Convierte una imagen PIL a un tensor RGB con forma [1, 3, H, W]."""
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    arr = np.asarray(pil_img).astype(np.float32) / 255.0  # H, W, 3 en [0, 1]
    return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)  # 1, 3, H, W


def _normalize_imagenet(img_t: torch.Tensor) -> torch.Tensor:
    """Aplica normalización ImageNet a un tensor de imagen RGB."""
    mean = img_t.new_tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
    std = img_t.new_tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
    return (img_t - mean) / std


# Stubs mínimos para reconstruir pickles heredados.

class BinarySegModel(nn.Module):
    """
    Stub mínimo para que pickle pueda reconstruir instancias antiguas.

    Durante el unpickle no se invoca __init__, pero la clase debe existir
    para resolver la referencia.
    """

    def __init__(self):
        super().__init__()

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        # Si el objeto serializado incluye mean/std, la normalización se aplica
        # aquí antes de delegar en el modelo interno.
        if hasattr(self, "mean") and hasattr(self, "std"):
            image = (image - self.mean) / self.std
        return self.model(image)

    # Métodos habituales de Lightning referenciados en algunos pickles.
    def log(self, *args, **kwargs): return None
    def log_dict(self, *args, **kwargs): return None
    def save_hyperparameters(self, *args, **kwargs): return None


class SemanticSegmentatorPyTorch:
    """Stub auxiliar para compatibilidad durante la deserialización."""

    def __init__(self):
        self.model = None
        self.trainer = None


class HuggingFaceToTorchDataset:
    """Stub auxiliar para compatibilidad durante la deserialización."""

    def __init__(self, *args, **kwargs):
        pass


class HuggingFaceToTorchDataset_onlyImage:
    """Stub auxiliar para compatibilidad durante la deserialización."""

    def __init__(self, *args, **kwargs):
        pass


def _inject_symbols_into_main():
    """
    Inyecta en __main__ los símbolos que algunos pickles antiguos esperan
    resolver durante la deserialización.
    """
    main_mod = sys.modules.get("__main__")
    if main_mod is None:
        return
    setattr(main_mod, "BinarySegModel", BinarySegModel)
    setattr(main_mod, "SemanticSegmentatorPyTorch", SemanticSegmentatorPyTorch)
    setattr(main_mod, "HuggingFaceToTorchDataset", HuggingFaceToTorchDataset)
    setattr(
        main_mod,
        "HuggingFaceToTorchDataset_onlyImage",
        HuggingFaceToTorchDataset_onlyImage,
    )


# Compatibilidad con segmentation_models_pytorch.

def _patch_smp_compat():
    """
    Aplica ajustes de compatibilidad para cambios de nombres internos en
    segmentation_models_pytorch.
    """
    try:
        from segmentation_models_pytorch.decoders.unet import (
            decoder as unet_decoder,
        )
        if (
            hasattr(unet_decoder, "UnetDecoderBlock")
            and not hasattr(unet_decoder, "DecoderBlock")
        ):
            unet_decoder.DecoderBlock = unet_decoder.UnetDecoderBlock
    except Exception:
        pass


def _patch_unet_interpolation_mode(net: nn.Module, default: str = "nearest"):
    """
    Añade interpolation_mode a los bloques del decoder que no lo tengan,
    para mantener compatibilidad con modelos serializados de versiones
    anteriores.
    """
    for m in net.modules():
        if m.__class__.__name__ in ("UnetDecoderBlock", "DecoderBlock"):
            if not hasattr(m, "interpolation_mode"):
                m.interpolation_mode = default


# Unpickling seguro sin dependencias de Lightning.

class _DummyMeta(type):
    """Permite resolver atributos de clase ausentes durante el unpickle."""

    def __getattr__(cls, name):
        return cls  # Placeholder para atributos como _Dummy.FITTING.

    def __call__(cls, *args, **kwargs):
        # Cuando pickle instancia la clase, devolvemos un objeto dict-like.
        obj = super().__call__()
        return obj


class _Dummy(dict, metaclass=_DummyMeta):
    """
    Reemplazo genérico para clases de Lightning ausentes durante el unpickle.

    Se comporta como un contenedor flexible:
    - soporta acceso por clave,
    - permite acceso por atributo,
    - y puede encadenarse como placeholder sin romper la carga.
    """

    def __init__(self, *args, **kwargs):
        super().__init__()

    def __getattr__(self, name):
        if name in self:
            return self[name]
        d = _Dummy()
        self[name] = d
        return d

    def __setattr__(self, name, value):
        self[name] = value

    def __call__(self, *args, **kwargs):
        return self

    def reduce(self, *args, **kwargs):
        return args[0] if args else None


class _SafeUnpickler(pickle.Unpickler):
    """Unpickler tolerante a dependencias opcionales
    no presentes en runtime."""

    _IGNORE_PREFIXES = (
        "pytorch_lightning",
        "lightning",
    )

    def find_class(self, module, name):
        if module.startswith(self._IGNORE_PREFIXES):
            return _Dummy
        return super().find_class(module, name)


def _pickle_load_safe(path: str):
    """Carga un pickle usando un unpickler tolerante a dependencias
    ausentes."""
    with open(path, "rb") as f:
        return _SafeUnpickler(f).load()


def _extract_core_module(obj) -> nn.Module:
    """
    Extrae el nn.Module utilizable para inferencia desde el objeto
    deserializado.
    """
    if isinstance(obj, nn.Module):
        return obj
    if hasattr(obj, "model") and isinstance(obj.model, nn.Module):
        return obj.model
    raise TypeError(
        f"No se pudo extraer nn.Module del objeto pickle: {type(obj)}"
    )


class _PickleInferWrapper(nn.Module):
    """
    Envuelve el modelo cargado para unificar la normalización y la salida.

    - Si el modelo ya incorpora mean y std, no se normaliza fuera.
    - Si no los incorpora, se aplica normalización ImageNet.
    - Si la salida parece estar en logits, se convierte a probabilidades
      mediante sigmoid.
    """

    def __init__(self, core: nn.Module):
        super().__init__()
        self.core = core
        self.has_internal_norm = hasattr(core, "mean") and hasattr(core, "std")

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if not self.has_internal_norm:
            x = _normalize_imagenet(x)
        y = self.core(x)

        # Si la salida queda fuera de [0, 1], se interpreta como logits.
        y_min = float(y.min().detach().cpu())
        y_max = float(y.max().detach().cpu())
        if y_min < 0.0 or y_max > 1.0:
            y = torch.sigmoid(y)
        return y


# Carga cacheada del modelo serializado.

@lru_cache(maxsize=8)
def load_fold_pickle_models(
    models_dir: str,
    model_template: str,
    fold_id: int,
    use_gpu: bool,
):
    """
    Carga un modelo serializado, lo adapta para inferencia y lo deja
    preparado en el dispositivo correspondiente.

    Returns:
        tuple[list[nn.Module], torch.device]: Lista de modelos lista para
        inferencia y dispositivo asociado.
    """
    device = torch.device(
        "cuda" if (use_gpu and torch.cuda.is_available()) else "cpu"
    )

    _inject_symbols_into_main()
    _patch_smp_compat()

    fold = int(fold_id)
    p = os.path.join(models_dir, model_template.format(fold=fold))
    if not os.path.exists(p):
        raise FileNotFoundError(
            f"No se encontró el modelo PICKLE del fold {fold}: {p}"
        )

    obj = _pickle_load_safe(p)
    core = _extract_core_module(obj)
    _patch_unet_interpolation_mode(core, default="nearest")

    m = _PickleInferWrapper(core).to(device).eval()
    models = [m]

    return models, device


# Predicción de máscara binaria.

def predict_mask_ensemble(
    image_path: str,
    models_dir: str,
    model_template: str,
    use_gpu: bool,
    threshold: float = 0.5,
) -> np.ndarray:
    """
    Genera una máscara binaria a partir de la imagen indicada.

    La imagen se preprocesa, se ejecuta la inferencia con el modelo cargado y
    la salida se umbraliza para obtener una máscara binaria recortada al
    tamaño original.
    """
    with Image.open(image_path) as pil:
        w0, h0 = pil.size
        img_t = _pil_to_tensor_rgb(pil)

    img_t, _, _ = _pad_to_multiple_of_32(img_t)

    models, device = load_fold_pickle_models(
        models_dir=models_dir,
        model_template=model_template,
        fold_id=0,  # Implementación actual: carga el fold 0.
        use_gpu=use_gpu,
    )

    img_t = img_t.to(device)

    probs_sum = None
    with torch.inference_mode():
        for m in models:
            probs = m(img_t)
            probs_sum = probs if probs_sum is None else (probs_sum + probs)

    probs_avg = probs_sum / float(len(models))

    target_h, target_w = img_t.shape[-2:]
    if probs_avg.shape[-2:] != (target_h, target_w):
        probs_avg = F.interpolate(
            probs_avg,
            size=(target_h, target_w),
            mode="bilinear",
            align_corners=False,
        )

    mask = (probs_avg > threshold).to(torch.uint8)

    mask_np = mask.squeeze(0).squeeze(0).detach().cpu().numpy()
    return mask_np[:h0, :w0]


# Conversión de máscara a coordenadas de traza.

def mask_to_traces_points(mask: np.ndarray) -> Dict[str, List[int]]:
    """
    Convierte una máscara binaria en listas de coordenadas xs e ys.
    """
    ys, xs = np.where(mask > 0)
    if xs.size == 0:
        return {"xs": [], "ys": []}
    return {"xs": xs.astype(int).tolist(), "ys": ys.astype(int).tolist()}


def compute_traces_from_segmentation(
    image_path: str,
    models_dir: str,
    model_template: str,
    n_folds: int,
    use_gpu: bool,
) -> Dict[str, List[int]]:
    """
    Ejecuta la inferencia de segmentación y devuelve las coordenadas de traza
    en el formato esperado por el frontend.

    El parámetro n_folds se mantiene en la firma por compatibilidad con la
    configuración del pipeline, aunque en esta implementación no se utiliza de
    forma directa.
    """
    mask = predict_mask_ensemble(
        image_path=image_path,
        models_dir=models_dir,
        model_template=model_template,
        use_gpu=use_gpu,
        threshold=0.5,
    )
    return mask_to_traces_points(mask)
