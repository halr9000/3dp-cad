"""Thread-safe model registry for the 3DP CAD server.

Replaces the global `_models` dict with a class-based store that provides
thread-safe access, logging, and model lifecycle management.
"""

from __future__ import annotations

import threading
from typing import Any

from threedp.logging_config import get_logger

log = get_logger()


class ModelStore:
    """Thread-safe in-memory model registry.

    Stores build123d shapes along with metadata (bbox, volume, code).
    Each model is keyed by a user-provided string name.
    """

    def __init__(self) -> None:
        self._models: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def put(self, name: str, entry: dict[str, Any]) -> None:
        """Store a model entry.

        Args:
            name: Unique model name
            entry: Dict with keys: shape, code, bbox, volume
        """
        with self._lock:
            self._models[name] = entry
            log.info(
                "model_stored",
                extra={
                    "model_name": name,
                    "bbox": entry.get("bbox"),
                    "volume": entry.get("volume"),
                },
            )

    def get(self, name: str) -> dict[str, Any] | None:
        """Retrieve a model entry by name. Returns None if not found."""
        with self._lock:
            return self._models.get(name)

    def get_required(self, name: str) -> dict[str, Any]:
        """Retrieve a model entry, raising ValueError if not found."""
        entry = self.get(name)
        if entry is None:
            available = list(self._models.keys())
            raise ValueError(f"Model '{name}' not found. Available: {available}")
        return entry

    def has(self, name: str) -> bool:
        """Check if a model exists."""
        with self._lock:
            return name in self._models

    def delete(self, name: str) -> bool:
        """Delete a model. Returns True if it existed."""
        with self._lock:
            existed = name in self._models
            if existed:
                del self._models[name]
                log.info("model_deleted", extra={"model_name": name})
            return existed

    def list_models(self) -> list[dict[str, Any]]:
        """List all models with their metadata (without the shape object)."""
        with self._lock:
            return [
                {"name": n, "bbox": d.get("bbox"), "volume": d.get("volume")}
                for n, d in self._models.items()
            ]

    def names(self) -> list[str]:
        """Return a list of all model names."""
        with self._lock:
            return list(self._models.keys())

    def clear(self) -> None:
        """Remove all models (for testing or session reset)."""
        with self._lock:
            count = len(self._models)
            self._models.clear()
            log.info("store_cleared", extra={"models_removed": count})

    def __contains__(self, name: str) -> bool:
        """Support 'name in store' syntax."""
        return self.has(name)

    def __len__(self) -> int:
        """Return the number of stored models."""
        with self._lock:
            return len(self._models)


# ── Singleton ────────────────────────────────────────────────────────────────

_store: ModelStore | None = None


def get_store() -> ModelStore:
    """Return the global model store (lazy singleton)."""
    global _store
    if _store is None:
        _store = ModelStore()
    return _store
