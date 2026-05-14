"""
===============================================================================
Pruebas unitarias de inferencia de segmentación.

Este módulo cubre ramas internas de carga, validación y preprocesado
sin depender de modelos reales pesados.

Autor: Marcos Zamorano Lasso
Versión: 0.1
===============================================================================
"""

from __future__ import annotations

import pickle
import sys
import types

import numpy as np
import pytest
import torch
from PIL import Image
from torch import nn

import trazasytrazadas.segmentation_inference as seg


class ConstantMaskModel(nn.Module):
    def __init__(self, value: float = 1.0, channels: int = 1, scale: int = 1):
        """Inicializa el doble de prueba."""
        super().__init__()
        self.value = value
        self.channels = channels
        self.scale = scale

    def forward(self, x):
        """Devuelve una máscara constante para la inferencia simulada."""
        h = max(1, x.shape[-2] // self.scale)
        w = max(1, x.shape[-1] // self.scale)
        return torch.full(
            (x.shape[0], self.channels, h, w), self.value, device=x.device
        )


class DictOutputModel(nn.Module):
    def forward(self, x):
        """Devuelve una máscara constante para la inferencia simulada."""
        return {
            "logits": torch.ones(
                (1, 1, x.shape[-2], x.shape[-1]), device=x.device
            )
            * 2
        }


class TupleOutputModel(nn.Module):
    def forward(self, x):
        """Devuelve una máscara constante para la inferencia simulada."""
        return (
            "ignored",
            torch.ones((1, 1, x.shape[-2], x.shape[-1]), device=x.device),
        )


class DecoderBlock(nn.Module):
    pass


class ParentWithDecoder(nn.Module):
    def __init__(self):
        """Inicializa el doble de prueba."""
        super().__init__()
        self.block = DecoderBlock()


def test_tensor_preprocessing_and_stubs():
    """Verifica el comportamiento esperado en el caso previsto."""
    tensor = torch.zeros((1, 3, 32, 64))
    padded, pad_h, pad_w = seg._pad_to_multiple_of_32(tensor)
    assert padded is tensor
    assert (pad_h, pad_w) == (0, 0)

    tensor = torch.zeros((1, 3, 33, 34))
    padded, pad_h, pad_w = seg._pad_to_multiple_of_32(tensor)
    assert padded.shape[-2:] == (64, 64)
    assert (pad_h, pad_w) == (31, 30)

    pil = Image.new("L", (2, 3), color=255)
    rgb_tensor = seg._pil_to_tensor_rgb(pil)
    assert rgb_tensor.shape == (1, 3, 3, 2)
    normalized = seg._normalize_imagenet(rgb_tensor)
    assert normalized.shape == rgb_tensor.shape

    model = seg.BinarySegModel()
    model.model = ConstantMaskModel(value=0.25)
    model.mean = torch.zeros((1, 3, 1, 1))
    model.std = torch.ones((1, 3, 1, 1))
    assert model(torch.zeros((1, 3, 4, 4))).shape == (1, 1, 4, 4)
    assert model.log() is None
    assert model.log_dict() is None
    assert model.save_hyperparameters() is None

    segmentator = seg.SemanticSegmentatorPyTorch()
    assert segmentator.model is None
    assert segmentator.trainer is None
    assert seg.HuggingFaceToTorchDataset() is not None
    assert seg.HuggingFaceToTorchDataset_onlyImage() is not None


def test_inject_symbols_and_patch_helpers(monkeypatch):
    """Verifica el comportamiento esperado en el caso previsto."""
    fake_main = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "__main__", fake_main)
    seg._inject_symbols_into_main()
    assert fake_main.BinarySegModel is seg.BinarySegModel

    monkeypatch.setitem(sys.modules, "__main__", None)
    seg._inject_symbols_into_main()

    fake_decoder = types.SimpleNamespace(UnetDecoderBlock=object)
    fake_unet = types.ModuleType("segmentation_models_pytorch.decoders.unet")
    fake_unet.decoder = fake_decoder
    monkeypatch.setitem(
        sys.modules,
        "segmentation_models_pytorch",
        types.ModuleType("segmentation_models_pytorch"),
    )
    monkeypatch.setitem(
        sys.modules,
        "segmentation_models_pytorch.decoders",
        types.ModuleType("segmentation_models_pytorch.decoders"),
    )
    monkeypatch.setitem(
        sys.modules, "segmentation_models_pytorch.decoders.unet", fake_unet
    )
    seg._patch_smp_compat()
    assert fake_decoder.DecoderBlock is fake_decoder.UnetDecoderBlock

    parent = ParentWithDecoder()
    assert not hasattr(parent.block, "interpolation_mode")
    seg._patch_unet_interpolation_mode(parent, default="bilinear")
    assert parent.block.interpolation_mode == "bilinear"


def test_dummy_and_safe_unpickler_behaviour(tmp_path):
    """Verifica el comportamiento esperado en el caso previsto."""
    dummy = seg._Dummy()
    dummy.answer = 42
    assert dummy["answer"] == 42
    assert isinstance(dummy.missing, seg._Dummy)
    assert dummy() is dummy
    assert dummy.reduce("x") == "x"
    assert dummy.reduce() is None
    assert seg._Dummy.UNKNOWN is seg._Dummy

    payload = tmp_path / "payload.pkl"
    with payload.open("wb") as fh:
        pickle.dump({"model": ConstantMaskModel()}, fh)
    loaded = seg._pickle_load_safe(str(payload))
    assert isinstance(loaded["model"], ConstantMaskModel)

    assert seg._SafeUnpickler.find_class.__qualname__.startswith(
        "_SafeUnpickler"
    )


def test_state_dict_and_core_module_extraction():
    """Verifica el comportamiento esperado en el caso previsto."""
    state = {"layer.weight": torch.zeros(1), "nested": {"bias": torch.ones(1)}}
    assert seg._looks_like_state_dict(state)
    assert not seg._looks_like_state_dict({})
    assert not seg._looks_like_state_dict({"x": object()})

    core = ConstantMaskModel()
    assert seg._extract_core_module(core) is core

    holder = types.SimpleNamespace(model=core)
    assert seg._extract_core_module(holder) is core

    for key in ("model", "module", "net", "network"):
        assert seg._extract_core_module({key: core}) is core

    for key in ("state_dict", "model_state_dict", "weights"):
        with pytest.raises(ValueError):
            seg._extract_core_module({key: state})

    with pytest.raises(ValueError):
        seg._extract_core_module(state)
    with pytest.raises(TypeError):
        seg._extract_core_module(object())


def test_output_extraction_and_infer_wrapper():
    """Verifica el comportamiento esperado en el caso previsto."""
    tensor = torch.ones((1, 1, 2, 2))
    assert seg._extract_tensor_output(tensor) is tensor
    assert seg._extract_tensor_output(["x", tensor]) is tensor
    assert seg._extract_tensor_output({"mask": tensor}) is tensor
    assert seg._extract_tensor_output({"other": tensor}) is tensor
    with pytest.raises(TypeError):
        seg._extract_tensor_output({"other": object()})

    wrapper = seg._InferWrapper(DictOutputModel(), normalize_input=True)
    output = wrapper(torch.zeros((1, 3, 4, 4)))
    assert output.min() >= 0
    assert output.max() <= 1

    core = ConstantMaskModel()
    core.mean = torch.zeros((1, 3, 1, 1))
    core.std = torch.ones((1, 3, 1, 1))
    pickle_wrapper = seg._PickleInferWrapper(core)
    assert not pickle_wrapper.normalize_input


def test_loader_kind_and_model_loading_branches(monkeypatch, tmp_path):
    """Verifica la gestión de modelos en el caso previsto."""
    device = torch.device("cpu")
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"model")

    assert (
        seg._infer_loader_kind_from_filename("x_state_dict.pth")
        == "state_dict"
    )
    assert (
        seg._infer_loader_kind_from_filename("x_infer.pt")
        == "torchscript_infer"
    )
    assert (
        seg._infer_loader_kind_from_filename("x.pt") == "torchscript_network"
    )
    assert seg._infer_loader_kind_from_filename(None) == "auto"

    monkeypatch.setattr(
        seg,
        "_torch_load_compat",
        lambda path, device: {"model": ConstantMaskModel()},
    )
    model, kind = seg._load_model_for_inference(
        str(model_path), device=device, loader_kind="state_dict"
    )
    assert kind == "torch_module"
    assert isinstance(model, seg._PickleInferWrapper)

    model, kind = seg._load_model_for_inference(
        str(model_path), device=device, loader_kind="torch_module"
    )
    assert kind == "torch_module"

    monkeypatch.setattr(
        seg, "_pickle_load_safe", lambda path: {"net": ConstantMaskModel()}
    )
    model, kind = seg._load_model_for_inference(
        str(model_path), device=device, loader_kind="pickle"
    )
    assert kind == "pickle"

    monkeypatch.setattr(
        seg, "_torch_jit_load_compat", lambda path, device: ConstantMaskModel()
    )
    model, kind = seg._load_model_for_inference(
        str(model_path), device=device, loader_kind="torchscript_network"
    )
    assert kind == "torchscript_network"
    assert model.normalize_input

    model, kind = seg._load_model_for_inference(
        str(model_path), device=device, loader_kind="torchscript_infer"
    )
    assert kind == "torchscript_infer"
    assert not model.normalize_input

    model, kind = seg._load_model_for_inference(
        str(model_path), device=device, loader_kind="auto"
    )
    assert kind == "torchscript_infer"

    def fail_jit(path, device):
        """Simula un fallo del cargador TorchScript."""
        raise RuntimeError("jit failed")

    monkeypatch.setattr(seg, "_torch_jit_load_compat", fail_jit)
    model, kind = seg._load_model_for_inference(
        str(model_path), device=device, loader_kind="auto"
    )
    assert kind == "torch_module"

    def fail_torch(path, device):
        """Simula un fallo del cargador de PyTorch."""
        raise RuntimeError("torch failed")

    monkeypatch.setattr(seg, "_torch_load_compat", fail_torch)
    model, kind = seg._load_model_for_inference(
        str(model_path), device=device, loader_kind="auto"
    )
    assert kind == "pickle"

    monkeypatch.setattr(
        seg,
        "_pickle_load_safe",
        lambda path: (_ for _ in ()).throw(RuntimeError("pickle failed")),
    )
    with pytest.raises(ValueError):
        seg._load_model_for_inference(
            str(model_path), device=device, loader_kind="auto"
        )

    monkeypatch.setattr(
        seg,
        "_torch_load_compat",
        lambda path, device: {"state_dict": {"w": torch.ones(1)}},
    )
    with pytest.raises(ValueError):
        seg._load_model_for_inference(
            str(model_path), device=device, loader_kind="auto"
        )


def test_cached_loader_missing_and_success(monkeypatch, tmp_path):
    """Verifica el comportamiento esperado en el caso previsto."""
    seg.load_model_file_models.cache_clear()
    with pytest.raises(FileNotFoundError):
        seg.load_model_file_models(str(tmp_path), "missing", False)

    model_path = tmp_path / "modelo"
    model_path.write_bytes(b"x")
    monkeypatch.setattr(
        seg,
        "read_fold_metadata",
        lambda name, models_dir=None: {"loader_kind": "pickle"},
    )
    monkeypatch.setattr(
        seg,
        "_load_model_for_inference",
        lambda path, device, loader_kind: (ConstantMaskModel(), loader_kind),
    )
    models, device = seg.load_model_file_models(str(tmp_path), "modelo", False)
    assert len(models) == 1
    assert str(device) == "cpu"

    (tmp_path / "fold.3").write_bytes(b"x")
    seg.load_fold_pickle_models.cache_clear()
    models, device = seg.load_fold_pickle_models(
        str(tmp_path), "fold.{fold}", 3, False
    )
    assert len(models) == 1


def test_prediction_and_compute_traces(monkeypatch, tmp_path):
    """Verifica el flujo de trazas en el caso previsto."""
    image_path = tmp_path / "img.png"
    Image.new("RGB", (5, 6), color="white").save(image_path)

    monkeypatch.setattr(seg, "get_active_fold_name", lambda **kwargs: None)
    with pytest.raises(FileNotFoundError):
        seg.predict_mask_ensemble(
            str(image_path), str(tmp_path), "fold.{fold}", False
        )

    monkeypatch.setattr(seg, "get_active_fold_name", lambda **kwargs: "modelo")
    monkeypatch.setattr(
        seg,
        "load_model_file_models",
        lambda models_dir, model_name, use_gpu: (
            [ConstantMaskModel(value=10.0, scale=2)],
            torch.device("cpu"),
        ),
    )
    mask = seg.predict_mask_ensemble(
        str(image_path), str(tmp_path), "fold.{fold}", False, threshold=0.5
    )
    assert mask.shape == (6, 5)
    assert mask.sum() == 30

    points = seg.compute_traces_from_segmentation(
        str(image_path), str(tmp_path), "fold.{fold}", 1, False
    )
    assert len(points["xs"]) == 30

    assert seg.mask_to_traces_points(np.zeros((2, 2), dtype=np.uint8)) == {
        "xs": [],
        "ys": [],
    }
    assert seg.mask_to_traces_points(np.array([[0, 1]], dtype=np.uint8)) == {
        "xs": [1],
        "ys": [0],
    }


def test_validation_tensor_output_coercion_and_model_file_validation(
    monkeypatch, tmp_path
):
    """Verifica la gestión de modelos en el caso previsto."""
    tensor = seg._make_validation_tensor(32)
    inverted = seg._make_validation_tensor(32, inverted=True)
    assert tensor.shape == (1, 3, 32, 32)
    assert not torch.equal(tensor, inverted)

    output3d = torch.ones((1, 32, 32))
    assert seg._coerce_validation_output(
        output3d, target_hw=(32, 32)
    ).shape == (1, 1, 32, 32)

    with pytest.raises(TypeError):
        seg._coerce_validation_output("bad", target_hw=(32, 32))
    with pytest.raises(ValueError):
        seg._coerce_validation_output(torch.ones((1, 1)), target_hw=(32, 32))
    with pytest.raises(ValueError):
        seg._coerce_validation_output(
            torch.ones((1, 2, 32, 32)), target_hw=(32, 32)
        )
    bad = torch.ones((1, 1, 32, 32))
    bad[0, 0, 0, 0] = float("nan")
    with pytest.raises(ValueError):
        seg._coerce_validation_output(bad, target_hw=(32, 32))

    small = torch.ones((1, 1, 16, 16))
    assert seg._coerce_validation_output(small, target_hw=(32, 32)).shape == (
        1,
        1,
        32,
        32,
    )

    with pytest.raises(FileNotFoundError):
        seg.validate_fold_model_file(str(tmp_path / "missing"))

    model_path = tmp_path / "modelo.pt"
    model_path.write_bytes(b"x")
    monkeypatch.setattr(
        seg,
        "_load_model_for_inference",
        lambda path, device, loader_kind: (
            ConstantMaskModel(),
            "torchscript_infer",
        ),
    )
    metadata = seg.validate_fold_model_file(
        str(model_path), image_size=33, source_filename="modelo_infer.pt"
    )
    assert metadata["image_size"] == 64
    assert metadata["loader_kind"] == "torchscript_infer"
    assert metadata["positive_pixels"] > 0

    monkeypatch.setattr(
        seg,
        "_load_model_for_inference",
        lambda path, device, loader_kind: (_ for _ in ()).throw(
            RuntimeError("boom")
        ),
    )
    with pytest.raises(ValueError):
        seg.validate_fold_model_file(str(model_path))

    monkeypatch.setattr(
        seg,
        "_load_model_for_inference",
        lambda path, device, loader_kind: (_ for _ in ()).throw(
            ValueError("bad model")
        ),
    )
    with pytest.raises(ValueError, match="bad model"):
        seg.validate_fold_model_file(str(model_path))
