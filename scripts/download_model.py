"""Download the all-MiniLM-L6-v2 ONNX export + tokenizer into data/models (idempotent)."""
import pathlib

from huggingface_hub import hf_hub_download

DEST = pathlib.Path(__file__).resolve().parent.parent / "data" / "models" / "all-MiniLM-L6-v2"
for f in ("onnx/model.onnx", "tokenizer.json", "config.json"):
    if (DEST / f).exists():
        print("present", f)
        continue
    print("downloaded", hf_hub_download("sentence-transformers/all-MiniLM-L6-v2", f, local_dir=str(DEST)))
