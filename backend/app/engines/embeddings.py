"""Sentence embeddings for semantic role-fit and span attribution.

Primary: all-MiniLM-L6-v2 (the TRD model) executed with ONNX Runtime on CPU, using the
official ONNX export from the sentence-transformers repository and the same mean-pooling +
L2-normalisation that sentence-transformers applies. ONNX Runtime is used instead of PyTorch
because PyTorch DLLs can be blocked by Windows Application Control (ADR-002).

Fallback: a deterministic hashed bag-of-words embedding. When active, `status()["mode"]`
says "lexical-fallback" and the dashboard shows it; it is never presented as MiniLM.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np

from ..config import settings

_TOKEN = re.compile(r"[a-z0-9]+")
_SYNONYMS = {"quotes": "quote", "prices": "price", "suppliers": "supplier", "requests": "request",
             "purchase": "procure", "procurement": "procure", "pr": "request", "documents": "document",
             "salaries": "salary", "employees": "employee", "fetch": "retrieve", "get": "retrieve",
             "read": "retrieve", "create": "raise", "compare": "compare"}


class Embedder:
    def __init__(self) -> None:
        self.mode = "uninitialised"
        self.error: str | None = None
        self.load_ms: float | None = None
        self._session = None
        self._tok = None
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._cache_max = 20000
        self.calls = 0
        self.cache_hits = 0

    # ------------------------------------------------------------------ loading
    def model_dir(self) -> Path:
        return settings.data_dir / "models" / settings.embedding_model

    def load(self) -> None:
        with self._lock:
            if self.mode != "uninitialised":
                return
            t0 = time.perf_counter()
            if not settings.embeddings_enabled:
                self.mode, self.error = "lexical-fallback", "disabled by TETHER_EMBEDDINGS=0"
                return
            try:
                import onnxruntime as ort
                from tokenizers import Tokenizer
                d = self.model_dir()
                model = d / "onnx" / "model.onnx"
                if not model.exists():
                    raise FileNotFoundError(f"{model} missing (run scripts/download_model.py)")
                tok = Tokenizer.from_file(str(d / "tokenizer.json"))
                tok.enable_truncation(max_length=128)
                tok.enable_padding(pad_id=0, pad_token="[PAD]")
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 2
                opts.log_severity_level = 3
                self._session = ort.InferenceSession(str(model), sess_options=opts, providers=["CPUExecutionProvider"])
                self._inputs = {i.name for i in self._session.get_inputs()}
                self._tok = tok
                self.mode = "minilm-onnx"
            except Exception as exc:  # environment problem -> explicit fallback
                self.mode, self.error = "lexical-fallback", f"{type(exc).__name__}: {exc}"
            self.load_ms = (time.perf_counter() - t0) * 1000

    # ------------------------------------------------------------------ encoding
    def _encode_minilm(self, texts: list[str]) -> np.ndarray:
        enc = self._tok.encode_batch(texts)
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        out = self._session.run(None, feed)[0]  # (batch, seq, 384)
        m = mask[..., None].astype(np.float32)
        pooled = (out * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
        return pooled / np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)

    @staticmethod
    def _encode_lexical(texts: list[str]) -> np.ndarray:
        dim = 512
        out = np.zeros((len(texts), dim), dtype=np.float32)
        for i, t in enumerate(texts):
            toks = [_SYNONYMS.get(w, w) for w in _TOKEN.findall(t.lower())]
            grams = toks + [a + "_" + b for a, b in zip(toks, toks[1:])]
            for g in grams:
                h = int(hashlib.md5(g.encode()).hexdigest(), 16)
                out[i, h % dim] += 1.0 if (h >> 9) & 1 else -1.0
                out[i, (h >> 13) % dim] += 0.5
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out

    def encode(self, texts: list[str]) -> np.ndarray:
        if self.mode == "uninitialised":
            self.load()
        result: list[np.ndarray | None] = []
        missing: list[str] = []
        for t in texts:
            self.calls += 1
            v = self._cache.get(t)
            if v is not None:
                self.cache_hits += 1
                self._cache.move_to_end(t)
            else:
                missing.append(t)
            result.append(v)
        if missing:
            uniq = list(dict.fromkeys(missing))
            with self._lock:
                vecs = self._encode_minilm(uniq) if self.mode == "minilm-onnx" else self._encode_lexical(uniq)
            for t, v in zip(uniq, vecs):
                self._cache[t] = v
                if len(self._cache) > self._cache_max:
                    self._cache.popitem(last=False)
            result = [self._cache[t] if r is None else r for t, r in zip(texts, result)]
        return np.vstack(result) if result else np.zeros((0, 384), dtype=np.float32)

    def similarity(self, a: str, others: list[str]) -> np.ndarray:
        vecs = self.encode([a] + others)
        return vecs[1:] @ vecs[0]

    def status(self) -> dict:
        return {"mode": self.mode, "model": settings.embedding_model, "error": self.error,
                "load_ms": round(self.load_ms, 1) if self.load_ms else None,
                "cache_size": len(self._cache), "calls": self.calls, "cache_hits": self.cache_hits}


embedder = Embedder()
