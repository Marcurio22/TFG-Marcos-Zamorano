"""
Conversión de modelos entrenados a formato TorchScript.

Script auxiliar utilizado para generar artefactos exportables a partir de los
modelos de segmentación entrenados durante la fase experimental.

Autor: Marcos Zamorano Lasso
Versión: 1.0
"""
import working_example_unet_mamba_simple as ws
import os
import sys
import json
import pickle
import torch
import importlib
import __main__

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
print(sys.path)

os.environ["SKIP_DATASET_LOADING"] = "1"


# Registra en __main__ las clases necesarias para cargar pickles antiguos.
for name in [
    "BinarySegModel",
    "SemanticSegmentatorPyTorch",
    "HuggingFaceToTorchDataset",
    "HuggingFaceToTorchDataset_onlyImage",
    "SemanticSegmentator",
]:
    if hasattr(ws, name):
        setattr(__main__, name, getattr(ws, name))

try:
    unet_dec = importlib.import_module(
        "segmentation_models_pytorch.decoders.unet.decoder")
    has_decoder_block = hasattr(unet_dec, "DecoderBlock")
    has_unet_decoder_block = hasattr(unet_dec, "UnetDecoderBlock")
    if not has_decoder_block and has_unet_decoder_block:
        unet_dec.DecoderBlock = unet_dec.UnetDecoderBlock
except Exception as e:
    print("Aviso: no pude aplicar monkeypatch SMP:", repr(e))

SRC_DIR = r"."
DST_DIR = r"./model_torchscript"
os.makedirs(DST_DIR, exist_ok=True)

prefix = (
    "data.8x(100imgs)_miou_method.unet_tu-mambaout_base_wide_rw_lr"
    ".9e-05_epochs.60_fold."
)

device = "cpu"

# Parámetros de normalización usados durante inferencia.
preprocess = {
    "mean": [0.485, 0.456, 0.406],
    "std":  [0.229, 0.224, 0.225],
}
preprocess_path = os.path.join(DST_DIR, "preprocess.json")
with open(preprocess_path, "w", encoding="utf-8") as f:
    json.dump(preprocess, f, indent=2)


def load_any(path: str):
    """Carga un modelo guardado con pickle o con torch.load."""
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return torch.load(path, map_location=device, weights_only=False)


def extract_pure_net(obj) -> torch.nn.Module:
    """Extrae la red PyTorch exportable desde el objeto cargado."""
    if hasattr(obj, "model"):
        m = obj.model

        if (hasattr(m, "model") and
                isinstance(m.model, torch.nn.Module)):
            return m.model

        is_not_lightning = (
            not m.__class__.__module__.startswith("pytorch_lightning"))
        if isinstance(m, torch.nn.Module) and is_not_lightning:
            return m

    if isinstance(obj, torch.nn.Module):
        if obj.__class__.__module__.startswith("pytorch_lightning"):
            if (hasattr(obj, "model") and
                    isinstance(obj.model, torch.nn.Module)):
                return obj.model
            raise RuntimeError(
                "Checkpoint es LightningModule y no encuentro "
                "obj.model con la red pura.")
        return obj

    raise RuntimeError(
        f"No puedo extraer un nn.Module exportable. Tipo={type(obj)}")


class InferWrapper(torch.nn.Module):
    """Modelo de inferencia con normalización y sigmoid integradas."""

    def __init__(self, net: torch.nn.Module, mean, std):
        """Inicializa la red y registra los parámetros de normalización."""
        super().__init__()
        self.net = net
        self.register_buffer("mean", torch.tensor(mean).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(std).view(1, 3, 1, 1))

    def forward(self, x):
        """Ejecuta la inferencia normalizada sobre el tensor de entrada."""
        x = (x - self.mean) / self.std
        logits = self.net(x)
        return torch.sigmoid(logits)


for fold in range(10):
    src = os.path.join(SRC_DIR, f"{prefix}{fold}")
    print("Cargando:", src)

    obj = load_any(src)

    net = extract_pure_net(obj).to(device)
    net.eval()

    def patch_unet_decoder_interpolation_mode(
        net: torch.nn.Module, default="nearest"
    ):
        """Ajusta bloques del decoder que no declaran modo de interpolación."""
        for m in net.modules():
            name = m.__class__.__name__
            if name in ("UnetDecoderBlock", "DecoderBlock"):
                if not hasattr(m, "interpolation_mode"):
                    m.interpolation_mode = default

    patch_unet_decoder_interpolation_mode(net, default="nearest")

    sd_path = os.path.join(DST_DIR, f"unet_fold_{fold}.state_dict.pth")
    torch.save(net.state_dict(), sd_path)
    print("State_dict guardado:", sd_path)

    dummy = torch.randn(1, 3, 512, 512)

    print("Trazando TorchScript (net puro) fold", fold)
    ts_net = torch.jit.trace(net, dummy, strict=False)
    dst_net = os.path.join(DST_DIR, f"unet_fold_{fold}.pt")
    ts_net.save(dst_net)
    print("Guardado:", dst_net)

    print("Trazando TorchScript (wrapper inferencia) fold", fold)
    infer = InferWrapper(net, preprocess["mean"], preprocess["std"]).eval()
    ts_infer = torch.jit.trace(infer, dummy, strict=False)
    dst_infer = os.path.join(DST_DIR, f"unet_fold_{fold}_infer.pt")
    ts_infer.save(dst_infer)
    print("Guardado:", dst_infer)

print("Fin. Modelos TorchScript en:", DST_DIR)
