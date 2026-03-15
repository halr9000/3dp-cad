"""Tests for model_store module."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from threedp.model_store import ModelStore


class TestModelStore:
    """Test ModelStore class."""

    @pytest.fixture
    def store(self) -> ModelStore:
        """Create a fresh store for each test."""
        return ModelStore()

    def _make_entry(self, name: str = "test", volume: float = 100.0) -> dict[str, Any]:
        """Create a minimal model entry."""
        return {
            "shape": None,  # We don't need real shapes for these tests
            "code": f"# code for {name}",
            "bbox": {"min": [0, 0, 0], "max": [10, 10, 10], "size": [10, 10, 10]},
            "volume": volume,
        }

    def test_put_and_get(self, store: ModelStore) -> None:
        """Test storing and retrieving a model."""
        entry = self._make_entry("box", 1000.0)
        store.put("box", entry)

        retrieved = store.get("box")
        assert retrieved is not None
        assert retrieved["code"] == "# code for box"
        assert retrieved["volume"] == 1000.0

    def test_get_missing_returns_none(self, store: ModelStore) -> None:
        """Test getting a non-existent model returns None."""
        assert store.get("nonexistent") is None

    def test_get_required_raises(self, store: ModelStore) -> None:
        """Test get_required raises ValueError for missing models."""
        with pytest.raises(ValueError, match="not found"):
            store.get_required("nonexistent")

    def test_get_required_returns_entry(self, store: ModelStore) -> None:
        """Test get_required returns entry when it exists."""
        entry = self._make_entry("cylinder")
        store.put("cylinder", entry)
        result = store.get_required("cylinder")
        assert result["volume"] == 100.0

    def test_has(self, store: ModelStore) -> None:
        """Test has method."""
        assert not store.has("sphere")
        store.put("sphere", self._make_entry("sphere"))
        assert store.has("sphere")

    def test_contains_operator(self, store: ModelStore) -> None:
        """Test 'in' operator."""
        assert "gear" not in store
        store.put("gear", self._make_entry("gear"))
        assert "gear" in store

    def test_delete(self, store: ModelStore) -> None:
        """Test deleting a model."""
        store.put("temp", self._make_entry("temp"))
        assert store.has("temp")

        result = store.delete("temp")
        assert result is True
        assert not store.has("temp")

    def test_delete_nonexistent(self, store: ModelStore) -> None:
        """Test deleting a non-existent model returns False."""
        assert store.delete("nope") is False

    def test_list_models(self, store: ModelStore) -> None:
        """Test listing all models."""
        store.put("a", self._make_entry("a", 100.0))
        store.put("b", self._make_entry("b", 200.0))

        models = store.list_models()
        assert len(models) == 2
        names = {m["name"] for m in models}
        assert names == {"a", "b"}

    def test_list_models_empty(self, store: ModelStore) -> None:
        """Test listing when store is empty."""
        assert store.list_models() == []

    def test_names(self, store: ModelStore) -> None:
        """Test names method."""
        store.put("x", self._make_entry("x"))
        store.put("y", self._make_entry("y"))
        assert set(store.names()) == {"x", "y"}

    def test_clear(self, store: ModelStore) -> None:
        """Test clearing all models."""
        store.put("m1", self._make_entry("m1"))
        store.put("m2", self._make_entry("m2"))
        assert len(store) == 2

        store.clear()
        assert len(store) == 0
        assert store.list_models() == []

    def test_len(self, store: ModelStore) -> None:
        """Test len() operator."""
        assert len(store) == 0
        store.put("one", self._make_entry("one"))
        assert len(store) == 1
        store.put("two", self._make_entry("two"))
        assert len(store) == 2

    def test_overwrite(self, store: ModelStore) -> None:
        """Test that putting with same name overwrites."""
        store.put("model", self._make_entry("model", 100.0))
        store.put("model", self._make_entry("model", 999.0))

        retrieved = store.get("model")
        assert retrieved["volume"] == 999.0
        assert len(store) == 1


class TestModelStoreThreadSafety:
    """Test ModelStore thread safety."""

    def test_concurrent_puts(self) -> None:
        """Test concurrent puts from multiple threads."""
        store = ModelStore()
        errors: list[Exception] = []

        def put_models(thread_id: int) -> None:
            try:
                for i in range(50):
                    name = f"model_t{thread_id}_i{i}"
                    entry = {
                        "shape": None,
                        "code": f"# {name}",
                        "bbox": {"min": [0, 0, 0], "max": [1, 1, 1], "size": [1, 1, 1]},
                        "volume": float(i),
                    }
                    store.put(name, entry)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=put_models, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        assert len(store) == 250  # 5 threads × 50 models

    def test_concurrent_read_write(self) -> None:
        """Test concurrent reads and writes."""
        store = ModelStore()
        store.put("shared", {
            "shape": None,
            "code": "# shared",
            "bbox": {"min": [0, 0, 0], "max": [1, 1, 1], "size": [1, 1, 1]},
            "volume": 42.0,
        })
        errors: list[Exception] = []

        def reader() -> None:
            try:
                for _ in range(100):
                    _ = store.get("shared")
                    _ = store.has("shared")
                    _ = "shared" in store
            except Exception as e:
                errors.append(e)

        def writer() -> None:
            try:
                for i in range(100):
                    store.put("shared", {
                        "shape": None,
                        "code": f"# v{i}",
                        "bbox": {"min": [0, 0, 0], "max": [1, 1, 1], "size": [1, 1, 1]},
                        "volume": float(i),
                    })
            except Exception as e:
                errors.append(e)

        threads = (
            [threading.Thread(target=reader) for _ in range(3)]
            + [threading.Thread(target=writer) for _ in range(2)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
