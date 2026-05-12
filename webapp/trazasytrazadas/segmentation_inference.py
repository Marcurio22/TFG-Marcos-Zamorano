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
import warnings
from functools import lru_cache
from typing import Any, List, Tuple, Dict

import numpy as np
from PIL import Image

import torch
import torch.nn as nn
import torch.nn.functional as F

from .model_store import (
    get_active_fold_name,
    read_fold_metadata,
)


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


def _looks_like_state_dict(obj: Any) -> bool:
    """Detecta diccionarios de pesos puros sin arquitectura ejecutable."""
    if not isinstance(obj, dict) or not obj:
        return False

    tensor_values = 0
    checked_values = 0
    for value in obj.values():
        if isinstance(value, torch.Tensor):
            tensor_values += 1
            checked_values += 1
        elif isinstance(value, dict):
            checked_values += 1
            if _looks_like_state_dict(value):
                tensor_values += 1
        else:
            checked_values += 1

        if checked_values >= 20:
            break

    return checked_values > 0 and tensor_values == checked_values


def _extract_core_module(obj) -> nn.Module:
    """
    Extrae el nn.Module utilizable para inferencia desde el objeto cargado.
    """
    if isinstance(obj, nn.Module):
        return obj

    if hasattr(obj, "model") and isinstance(obj.model, nn.Module):
        return obj.model

    if isinstance(obj, dict):
        for key in ("model", "module", "net", "network"):
            candidate = obj.get(key)
            if isinstance(candidate, nn.Module):
                return candidate

        for key in ("state_dict", "model_state_dict", "weights"):
            candidate = obj.get(key)
            if _looks_like_state_dict(candidate):
                raise ValueError(
                    "El archivo contiene pesos puros state_dict, pero no "
                    "incluye la arquitectura ejecutable. Convierte ese "
                    "archivo a un modelo de inferencia *_infer.pt o sube "
                    "un TorchScript completo."
                )

        if _looks_like_state_dict(obj):
            raise ValueError(
                "El archivo contiene pesos puros state_dict, pero no "
                "incluye la arquitectura ejecutable. Convierte ese archivo "
                "a un modelo de inferencia *_infer.pt o sube un TorchScript "
                "completo."
            )

    raise TypeError(
        f"No se pudo extraer nn.Module del objeto cargado: {type(obj)}"
    )


def _extract_tensor_output(output: Any) -> torch.Tensor:
    """Obtiene el tensor de máscara desde salidas comunes de modelos."""
    if isinstance(output, torch.Tensor):
        return output

    if isinstance(output, (list, tuple)):
        for item in output:
            if isinstance(item, torch.Tensor):
                return item

    if isinstance(output, dict):
        for key in ("mask", "masks", "out", "logits", "prediction", "pred"):
            item = output.get(key)
            if isinstance(item, torch.Tensor):
                return item
        for item in output.values():
            if isinstance(item, torch.Tensor):
                return item

    raise TypeError("El modelo no devuelve un tensor de PyTorch.")


class _InferWrapper(nn.Module):
    """
    Envuelve un modelo cargado para unificar entrada y salida.

    - Los pickles heredados y TorchScript de red pueden usar normalización
      ImageNet externa.
    - Los modelos *_infer.pt deben traer su propio preprocesado y se ejecutan
      con el tensor RGB en [0, 1].
    - Si la salida parece estar en logits, se convierte a probabilidades.
    """

    def __init__(self, core: nn.Module, *, normalize_input: bool):
        super().__init__()
        self.core = core
        self.normalize_input = normalize_input

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.normalize_input:
            x = _normalize_imagenet(x)

        y = _extract_tensor_output(self.core(x))

        y_min = float(y.min().detach().cpu())
        y_max = float(y.max().detach().cpu())
        if y_min < 0.0 or y_max > 1.0:
            y = torch.sigmoid(y)
        return y


class _PickleInferWrapper(_InferWrapper):
    """Wrapper compatible con el nombre histórico usado en tests."""

    def __init__(self, core: nn.Module):
        has_internal_norm = hasattr(core, "mean") and hasattr(core, "std")
        super().__init__(core, normalize_input=not has_internal_norm)


def _torch_load_compat(path: str, device: torch.device):
    """Carga artefactos de torch explicando que es una acción de admin."""
    return torch.load(path, map_location=device, weights_only=False)


def _torch_jit_load_compat(path: str, device: torch.device) -> nn.Module:
    """Carga TorchScript manteniendo compatibilidad con los folds actuales."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*torch\.jit\.load.*",
            category=DeprecationWarning,
        )
        return torch.jit.load(path, map_location=device).eval()


def _infer_loader_kind_from_filename(filename: str | None) -> str:
    """Clasifica el tipo esperado a partir del nombre de origen."""
    normalized = (filename or "").lower().strip()
    if normalized.endswith("_state_dict.pth"):
        return "state_dict"
    if normalized.endswith("_infer.pt"):
        return "torchscript_infer"
    if normalized.endswith(".pt"):
        return "torchscript_network"
    return "auto"


def _load_model_for_inference(
    model_path: str,
    *,
    device: torch.device,
    loader_kind: str = "auto",
) -> tuple[nn.Module, str]:
    """Carga un fold pickle/torch y devuelve un
        modelo listo para inferencia."""
    normalized_kind = (loader_kind or "auto").strip()

    if normalized_kind == "state_dict":
        obj = _torch_load_compat(model_path, device)
        core = _extract_core_module(obj)
        _patch_unet_interpolation_mode(core, default="nearest")
        return _PickleInferWrapper(core).to(device).eval(), "torch_module"

    if normalized_kind in {"torchscript_network", "torchscript_infer"}:
        module = _torch_jit_load_compat(model_path, device)
        normalize_input = normalized_kind == "torchscript_network"
        return (
            _InferWrapper(module, normalize_input=normalize_input)
            .to(device)
            .eval(),
            normalized_kind,
        )

    if normalized_kind == "torch_module":
        obj = _torch_load_compat(model_path, device)
        core = _extract_core_module(obj)
        _patch_unet_interpolation_mode(core, default="nearest")
        return _PickleInferWrapper(core).to(device).eval(), normalized_kind

    if normalized_kind == "pickle":
        obj = _pickle_load_safe(model_path)
        core = _extract_core_module(obj)
        _patch_unet_interpolation_mode(core, default="nearest")
        return _PickleInferWrapper(core).to(device).eval(), normalized_kind

    errors = []

    try:
        module = _torch_jit_load_compat(model_path, device)
    except Exception as exc:
        errors.append(exc)
    else:
        return (
            _InferWrapper(module, normalize_input=False).to(device).eval(),
            "torchscript_infer",
        )

    try:
        obj = _torch_load_compat(model_path, device)
        core = _extract_core_module(obj)
    except ValueError:
        raise
    except Exception as exc:
        errors.append(exc)
    else:
        _patch_unet_interpolation_mode(core, default="nearest")
        return _PickleInferWrapper(core).to(device).eval(), "torch_module"

    try:
        obj = _pickle_load_safe(model_path)
        core = _extract_core_module(obj)
    except ValueError:
        raise
    except Exception as exc:
        errors.append(exc)
    else:
        _patch_unet_interpolation_mode(core, default="nearest")
        return _PickleInferWrapper(core).to(device).eval(), "pickle"

    error = ValueError(
        "El archivo no se ha podido cargar como pickle, TorchScript ni "
        "módulo PyTorch compatible."
    )
    if errors:
        raise error from errors[-1]
    raise error

# Carga cacheada del modelo serializado.


@lru_cache(maxsize=8)
def load_model_file_models(
    models_dir: str,
    model_name: str,
    use_gpu: bool,
):
    """
    Carga un modelo serializado por nombre de fichero.

    Returns:
        tuple[list[nn.Module], torch.device]: Lista de modelos lista para
        inferencia y dispositivo asociado.
    """
    device = torch.device(
        "cuda" if (use_gpu and torch.cuda.is_available()) else "cpu"
    )

    _inject_symbols_into_main()
    _patch_smp_compat()

    normalized_name = (model_name or "").strip()
    p = os.path.join(models_dir, normalized_name)
    if not os.path.exists(p):
        raise FileNotFoundError(
            f"No se encontró el modelo activo {normalized_name}: {p}"
        )

    metadata = read_fold_metadata(normalized_name, models_dir=models_dir)
    loader_kind = metadata.get("loader_kind", "auto")

    model, _resolved_loader_kind = _load_model_for_inference(
        p,
        device=device,
        loader_kind=loader_kind,
    )
    return [model], device


@lru_cache(maxsize=8)
def load_fold_pickle_models(
    models_dir: str,
    model_template: str,
    fold_id: int,
    use_gpu: bool,
):
    """Carga legacy por índice fold.N conservando compatibilidad externa."""
    fold = int(fold_id)
    model_name = model_template.format(fold=fold)
    return load_model_file_models(
        models_dir=models_dir,
        model_name=model_name,
        use_gpu=use_gpu,
    )


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

    active_fold_name = get_active_fold_name(
        models_dir=models_dir,
        default_name="fold.0",
    )

    if active_fold_name is None:
        raise FileNotFoundError(
            "No hay ningún modelo validado activo para calcular trazas."
        )

    models, device = load_model_file_models(
        models_dir=models_dir,
        model_name=active_fold_name,
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


def _make_validation_tensor(size: int, inverted: bool = False) -> torch.Tensor:
    """Crea una imagen RGB sintética y determinista para validar modelos."""
    coords = torch.linspace(0.0, 1.0, steps=size)
    yy, xx = torch.meshgrid(coords, coords, indexing="ij")
    grid = torch.arange(size)
    checker = (
        ((grid[:, None] // 8 + grid[None, :] // 8) % 2)
        .to(dtype=torch.float32)
    )
    img = torch.stack((xx, yy, checker), dim=0).unsqueeze(0)
    if inverted:
        img = 1.0 - img
    return img


def _coerce_validation_output(
    output: torch.Tensor,
    *,
    target_hw: tuple[int, int],
) -> torch.Tensor:
    """Normaliza la salida de validación al contrato [1, 1, H, W]."""
    if not isinstance(output, torch.Tensor):
        raise TypeError("El modelo no devuelve un tensor de PyTorch.")

    if output.ndim == 3:
        output = output.unsqueeze(1)

    if output.ndim != 4:
        raise ValueError(
            "El modelo debe devolver un tensor con forma [B, 1, H, W]."
        )

    if output.shape[0] != 1 or output.shape[1] != 1:
        raise ValueError(
            "El sistema espera una segmentación binaria con un único canal."
        )

    if not torch.isfinite(output).all():
        raise ValueError("La salida del modelo contiene valores no finitos.")

    if output.shape[-2:] != target_hw:
        output = F.interpolate(
            output,
            size=target_hw,
            mode="bilinear",
            align_corners=False,
        )

    if not torch.isfinite(output).all():
        raise ValueError(
            "La salida interpolada del modelo contiene valores no finitos."
        )

    return output


def validate_fold_model_file(
    model_path: str,
    *,
    use_gpu: bool = False,
    image_size: int = 128,
    source_filename: str | None = None,
) -> dict:
    """
    Valida que un archivo serializado sea compatible con el pipeline actual.

    La comprobación carga el modelo con el loader correspondiente, ejecuta
    inferencia sobre imágenes RGB sintéticas y verifica que la salida sea una
    máscara binaria utilizable por mask_to_traces_points().
    """
    if not os.path.isfile(model_path):
        raise FileNotFoundError("El archivo de modelo no existe.")

    size = max(32, int(image_size or 128))
    if size % 32 != 0:
        size = int(np.ceil(size / 32) * 32)

    device = torch.device(
        "cuda" if (use_gpu and torch.cuda.is_available()) else "cpu"
    )
    loader_kind = _infer_loader_kind_from_filename(source_filename)

    try:
        _inject_symbols_into_main()
        _patch_smp_compat()

        model, resolved_loader_kind = _load_model_for_inference(
            model_path,
            device=device,
            loader_kind=loader_kind,
        )
        tensors = [
            _make_validation_tensor(size, inverted=False).to(device),
            _make_validation_tensor(size, inverted=True).to(device),
        ]

        outputs = []
        with torch.inference_mode():
            for tensor in tensors:
                output = model(tensor)
                output = _coerce_validation_output(
                    output,
                    target_hw=(size, size),
                )
                outputs.append(output.detach().cpu())

        mask = (outputs[0] > 0.5).to(torch.uint8)
        mask_np = mask.squeeze(0).squeeze(0).numpy()
        traces = mask_to_traces_points(mask_np)

        if not isinstance(traces.get("xs"), list):
            raise ValueError("La máscara generada no es convertible a trazas.")
        if not isinstance(traces.get("ys"), list):
            raise ValueError("La máscara generada no es convertible a trazas.")

        output_std = float(outputs[0].std().item())
        response_delta = float((outputs[0] - outputs[1]).abs().mean().item())

        return {
            "device": str(device),
            "image_size": size,
            "loader_kind": resolved_loader_kind,
            "positive_pixels": int(mask_np.sum()),
            "output_std": output_std,
            "response_delta": response_delta,
        }
    except (FileNotFoundError, ValueError):
        raise
    except Exception as exc:
        raise ValueError(
            "El archivo no se ha podido validar como modelo de segmentación."
        ) from exc


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
