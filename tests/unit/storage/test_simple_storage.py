"""
Тесты для SimpleAgentStorage.

Проверяют функциональность простого Key-Value хранилища
с поддержкой TTL и backward compatibility.
"""

import tempfile
import time
from pathlib import Path
from datetime import datetime, timedelta
import pytest

from thermo_agents.storage.simple_storage import SimpleAgentStorage, StorageEntry


class TestSimpleAgentStorage:
    """Тесты для SimpleAgentStorage."""

    def test_basic_operations(self):
        """Тест базовых операций set/get/delete."""
        storage = SimpleAgentStorage()

        # Test set and get
        storage.set("key1", "value1")
        assert storage.get("key1") == "value1"

        # Test get with default
        assert storage.get("nonexistent", "default") == "default"
        assert storage.get("nonexistent") is None

        # Test exists
        assert storage.exists("key1") is True
        assert storage.exists("nonexistent") is False

        # Test delete
        assert storage.delete("key1") is True
        assert storage.exists("key1") is False
        assert storage.delete("key1") is False

    def test_ttl_functionality(self):
        """Тест функциональности TTL."""
        storage = SimpleAgentStorage(default_ttl_seconds=1)  # 1 секунда

        # Set with custom TTL
        storage.set("key1", "value1", ttl_seconds=2)
        storage.set("key2", "value2")  # Uses default TTL

        # Should exist initially
        assert storage.get("key1") == "value1"
        assert storage.get("key2") == "value2"

        # Wait for default TTL to expire
        time.sleep(1.1)
        assert storage.get("key1") == "value1"  # Still has custom TTL
        assert storage.get("key2") is None  # Default TTL expired

        # Wait for custom TTL to expire
        time.sleep(1.1)
        assert storage.get("key1") is None  # Custom TTL expired

    def test_cleanup_expired(self):
        """Тест очистки просроченных записей."""
        storage = SimpleAgentStorage(default_ttl_seconds=1)

        storage.set("active", "value")
        storage.set("expired", "value", ttl_seconds=1)

        # Both should exist initially
        assert storage.exists("active")
        assert storage.exists("expired")

        # Wait for expiration
        time.sleep(1.1)

        # Cleanup should remove expired entries
        expired_count = storage.cleanup_expired()
        assert expired_count == 1

        # Active entry should still exist
        assert storage.exists("active")
        assert not storage.exists("expired")

    def test_typed_operations(self):
        """Тест типизированных операций."""
        storage = SimpleAgentStorage()

        # Test with string
        storage.set("str_key", "string_value")
        assert storage.get_typed("str_key", str) == "string_value"

        # Test type checking
        storage.set("int_key", 42)
        assert storage.get_typed("int_key", int) == 42

        # Type mismatch should raise error
        storage.set("str_key2", "string")
        with pytest.raises(TypeError):
            storage.get_typed("str_key2", int)

    def test_keys_filtering(self):
        """Тест фильтрации ключей."""
        storage = SimpleAgentStorage()

        storage.set("message:test1", "value1")
        storage.set("message:test2", "value2")
        storage.set("data:test1", "value3")
        storage.set("other:test", "value4")

        # Test pattern filtering
        message_keys = storage.keys("message:*")
        assert set(message_keys) == {"message:test1", "message:test2"}

        # Test all keys
        all_keys = storage.keys()
        assert set(all_keys) == {"message:test1", "message:test2", "data:test1", "other:test"}

    def test_size_and_stats(self):
        """Тест размера и статистики."""
        storage = SimpleAgentStorage()

        assert storage.size() == 0

        storage.set("key1", "value1")
        storage.set("key2", "value2")
        storage.set("key3", "value3")

        assert storage.size() == 3

        stats = storage.get_stats()
        assert stats["total_entries"] == 3
        assert stats["active_entries"] == 3
        assert stats["expired_entries"] == 0
        assert "str" in stats["type_distribution"]

    def test_entry_info(self):
        """Тест получения информации о записи."""
        storage = SimpleAgentStorage()

        storage.set("test_key", {"nested": "data"}, ttl_seconds=3600)

        info = storage.get_entry_info("test_key")
        assert info is not None
        assert info["key"] == "test_key"
        assert info["value_type"] == "dict"
        assert info["is_expired"] is False
        assert "expires_at" in info

        # Nonexistent key
        assert storage.get_entry_info("nonexistent") is None

    def test_ttl_update(self):
        """Тест обновления TTL."""
        storage = SimpleAgentStorage(default_ttl_seconds=1)

        storage.set("key1", "value1")
        assert storage.exists("key1")

        # Extend TTL
        assert storage.update_ttl("key1", 5) is True
        assert storage.exists("key1")

        # Wait for original TTL
        time.sleep(1.1)
        assert storage.exists("key1")  # Should still exist due to extended TTL

        # Nonexistent key
        assert storage.update_ttl("nonexistent", 5) is False

    def test_clear(self):
        """Тест очистки хранилища."""
        storage = SimpleAgentStorage()

        storage.set("key1", "value1")
        storage.set("key2", "value2")

        assert storage.size() == 2

        storage.clear()
        assert storage.size() == 0
        assert storage.get("key1") is None

    def test_file_persistence_simulation(self):
        """Тест симуляции файлового хранения."""
        storage = SimpleAgentStorage()

        # Simulate storing complex data
        complex_data = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "float": 3.14,
            "bool": True,
            "none": None
        }

        storage.set("complex", complex_data)
        retrieved = storage.get("complex")

        assert retrieved == complex_data
        assert retrieved["nested"]["key"] == "value"
        assert retrieved["list"] == [1, 2, 3]


class TestBackwardCompatibility:
    """Тесты обратной совместимости."""

    def test_message_passing_api(self):
        """Тест Message Passing API."""
        storage = SimpleAgentStorage()

        # Test session management
        storage.start_session("agent1", {"status": "active"})
        session = storage.get_session("agent1")
        assert session is not None
        assert session["status"] == "active"

        # Test message sending
        msg_id = storage.send_message(
            source_agent="agent1",
            target_agent="agent2",
            message_type="test",
            correlation_id="corr123",
            payload={"data": "test"}
        )
        assert msg_id is not None

        # Test message receiving
        messages = storage.receive_messages("agent2")
        assert len(messages) == 1
        assert messages[0]["source_agent"] == "agent1"
        assert messages[0]["target_agent"] == "agent2"
        assert messages[0]["message_type"] == "test"
        assert messages[0]["correlation_id"] == "corr123"
        assert messages[0]["payload"]["data"] == "test"

        # Message should be deleted after receiving
        messages = storage.receive_messages("agent2")
        assert len(messages) == 0

    def test_storage_snapshot(self):
        """Тест получения снимка хранилища."""
        storage = SimpleAgentStorage()

        storage.set("key1", "value1")
        storage.start_session("agent1", {"status": "active"})

        snapshot = storage.get_storage_snapshot()
        assert "stats" in snapshot
        assert "keys" in snapshot
        assert snapshot["stats"]["total_entries"] == 2
        assert "key1" in snapshot["keys"]

        # Test with content
        snapshot_with_content = storage.get_storage_snapshot(include_content=True)
        assert "content" in snapshot_with_content
        assert snapshot_with_content["content"]["key1"] == "value1"

    def test_legacy_api_compatibility(self):
        """Тест совместимости с legacy API."""
        storage = SimpleAgentStorage()

        # Test all legacy methods work
        storage.set("test", "value", ttl_seconds=10)
        assert storage.get("test") == "value"
        assert storage.exists("test")
        assert storage.delete("test")
        assert not storage.exists("test")

        # Test statistics
        stats = storage.get_stats()
        assert isinstance(stats, dict)
        assert "total_entries" in stats

        # Test cleanup
        storage.set("expired", "value", ttl_seconds=1)
        time.sleep(1.1)
        count = storage.cleanup_expired()
        assert count >= 0


class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_empty_storage(self):
        """Тест пустого хранилища."""
        storage = SimpleAgentStorage()

        assert storage.size() == 0
        assert storage.get("any") is None
        assert storage.exists("any") is False
        assert storage.delete("any") is False
        assert storage.keys() == []

    def test_large_data(self):
        """Тест больших объемов данных."""
        storage = SimpleAgentStorage()

        # Large string
        large_string = "x" * 10000
        storage.set("large", large_string)
        assert storage.get("large") == large_string

        # Large dict
        large_dict = {f"key{i}": f"value{i}" for i in range(1000)}
        storage.set("large_dict", large_dict)
        retrieved = storage.get("large_dict")
        assert len(retrieved) == 1000
        assert retrieved["key999"] == "value999"

    def test_special_characters(self):
        """Тест специальных символов в ключах и значениях."""
        storage = SimpleAgentStorage()

        # Special characters in keys
        special_keys = [
            "key with spaces",
            "key-with-dashes",
            "key_with_underscores",
            "key.with.dots",
            "key/with/slashes",
            "ключ на русском",
            "🔑 emoji key"
        ]

        for key in special_keys:
            value = f"value for {key}"
            storage.set(key, value)
            assert storage.get(key) == value

        # Special characters in values
        storage.set("unicode", "привет мир 🌍")
        storage.set("json_value", '{"nested": {"key": "value"}}')
        storage.set("list_value", [1, 2, "три", {"nested": True}])

        assert storage.get("unicode") == "привет мир 🌍"
        assert storage.get("json_value") == '{"nested": {"key": "value"}}'
        assert storage.get("list_value") == [1, 2, "три", {"nested": True}]

    def test_concurrent_access(self):
        """Тест одновременного доступа."""
        import threading

        storage = SimpleAgentStorage()
        results = []

        def worker(worker_id):
            for i in range(100):
                key = f"worker_{worker_id}_key_{i}"
                value = f"worker_{worker_id}_value_{i}"
                storage.set(key, value)
                retrieved = storage.get(key)
                results.append((worker_id, i, retrieved == value))

        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Check all operations succeeded
        assert len(results) == 500  # 5 workers * 100 operations each
        assert all(success for _, _, success in results)

    def test_zero_ttl(self):
        """Тест нулевого TTL (немедленное истечение)."""
        storage = SimpleAgentStorage()

        storage.set("immediate", "value", ttl_seconds=0)
        # Should be immediately expired
        assert storage.get("immediate") is None
        assert storage.exists("immediate") is False

    def test_negative_ttl(self):
        """Тест отрицательного TTL."""
        storage = SimpleAgentStorage()

        # Negative TTL should behave like immediate expiration
        storage.set("negative", "value", ttl_seconds=-1)
        assert storage.get("negative") is None


if __name__ == "__main__":
    pytest.main([__file__])