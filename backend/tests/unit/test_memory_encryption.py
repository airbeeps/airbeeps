"""
Unit tests for Memory Encryption.

Tests for MemoryEncryption class and key derivation.
"""

import os
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet


class TestMemoryEncryption:
    """Tests for MemoryEncryption class."""

    @pytest.fixture
    def valid_key(self):
        """Generate a valid Fernet key for testing."""
        return Fernet.generate_key().decode("utf-8")

    def test_init_with_valid_key(self, valid_key):
        """Should initialize with a valid key."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        encryption = MemoryEncryption(encryption_key=valid_key)
        assert encryption._cipher is not None

    def test_init_with_bytes_key(self, valid_key):
        """Should accept key as bytes."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        encryption = MemoryEncryption(encryption_key=valid_key.encode())
        assert encryption._cipher is not None

    def test_init_with_invalid_key(self):
        """Should raise ValueError for invalid key."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        with pytest.raises(ValueError, match="Invalid encryption key"):
            MemoryEncryption(encryption_key="not-a-valid-key")

    def test_init_from_environment(self, valid_key):
        """Should load key from environment variable."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        with patch.dict(os.environ, {"AIRBEEPS_MEMORY_ENCRYPTION_KEY": valid_key}):
            encryption = MemoryEncryption(encryption_key=None)
            assert encryption._cipher is not None

    def test_init_generates_key_when_missing(self):
        """Should generate ephemeral key when not configured."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        with patch.dict(os.environ, {}, clear=True):
            # Remove the key from environment
            env = os.environ.copy()
            env.pop("AIRBEEPS_MEMORY_ENCRYPTION_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                encryption = MemoryEncryption(encryption_key=None)
                assert encryption._cipher is not None

    def test_encrypt_decrypt_roundtrip(self, valid_key):
        """Should encrypt and decrypt correctly."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        encryption = MemoryEncryption(encryption_key=valid_key)
        original = "This is sensitive memory content"

        encrypted = encryption.encrypt(original)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == original

    def test_encrypt_produces_different_output(self, valid_key):
        """Encrypted data should differ from plaintext."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        encryption = MemoryEncryption(encryption_key=valid_key)
        original = "Secret data"

        encrypted = encryption.encrypt(original)

        assert encrypted != original
        assert len(encrypted) > len(original)

    def test_encrypt_empty_string(self, valid_key):
        """Should handle empty string."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        encryption = MemoryEncryption(encryption_key=valid_key)

        assert encryption.encrypt("") == ""
        assert encryption.decrypt("") == ""

    def test_encrypt_unicode_content(self, valid_key):
        """Should handle unicode content."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        encryption = MemoryEncryption(encryption_key=valid_key)
        original = "日本語テスト 🔐 émojis"

        encrypted = encryption.encrypt(original)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == original

    def test_encrypt_long_content(self, valid_key):
        """Should handle long content."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        encryption = MemoryEncryption(encryption_key=valid_key)
        original = "A" * 10000

        encrypted = encryption.encrypt(original)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == original

    def test_decrypt_with_wrong_key(self, valid_key):
        """Should fail to decrypt with wrong key."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        encryption1 = MemoryEncryption(encryption_key=valid_key)
        encryption2 = MemoryEncryption(encryption_key=Fernet.generate_key())

        encrypted = encryption1.encrypt("Secret data")

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption2.decrypt(encrypted)

    def test_decrypt_corrupted_data(self, valid_key):
        """Should fail to decrypt corrupted data."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        encryption = MemoryEncryption(encryption_key=valid_key)

        with pytest.raises(ValueError, match="Failed to decrypt"):
            encryption.decrypt("not-valid-encrypted-data")


class TestKeyGeneration:
    """Tests for key generation utilities."""

    def test_generate_key(self):
        """Should generate valid Fernet key."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        key = MemoryEncryption.generate_key()

        assert isinstance(key, str)
        # Fernet keys are 44 characters (32 bytes base64 encoded + padding)
        assert len(key) == 44

        # Key should be usable
        encryption = MemoryEncryption(encryption_key=key)
        assert encryption._cipher is not None

    def test_generate_key_unique(self):
        """Should generate unique keys each time."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        key1 = MemoryEncryption.generate_key()
        key2 = MemoryEncryption.generate_key()

        assert key1 != key2

    def test_derive_key_from_secret(self):
        """Should derive consistent key from secret."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        secret = "my-user-password"

        key1 = MemoryEncryption.derive_key_from_secret(secret)
        key2 = MemoryEncryption.derive_key_from_secret(secret)

        assert key1 == key2

    def test_derive_key_with_salt(self):
        """Should produce different keys with different salts."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        secret = "my-password"

        key1 = MemoryEncryption.derive_key_from_secret(secret, salt=b"salt1")
        key2 = MemoryEncryption.derive_key_from_secret(secret, salt=b"salt2")

        assert key1 != key2

    def test_derived_key_usable(self):
        """Derived key should work for encryption."""
        from airbeeps.agents.memory.encryption import MemoryEncryption

        secret = "user-secret-password"
        derived_key = MemoryEncryption.derive_key_from_secret(secret)

        encryption = MemoryEncryption(encryption_key=derived_key)

        original = "Test content"
        encrypted = encryption.encrypt(original)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == original


class TestGlobalEncryptionInstance:
    """Tests for global encryption instance management."""

    def test_get_memory_encryption(self):
        """Should return encryption instance."""
        from airbeeps.agents.memory.encryption import (
            get_memory_encryption,
            reset_encryption_instance,
        )

        # Reset to ensure clean state
        reset_encryption_instance()

        instance = get_memory_encryption()
        assert instance is not None

    def test_get_memory_encryption_singleton(self):
        """Should return same instance on repeated calls."""
        from airbeeps.agents.memory.encryption import (
            get_memory_encryption,
            reset_encryption_instance,
        )

        reset_encryption_instance()

        instance1 = get_memory_encryption()
        instance2 = get_memory_encryption()

        assert instance1 is instance2

    def test_reset_encryption_instance(self):
        """Should reset the global instance."""
        from airbeeps.agents.memory.encryption import (
            get_memory_encryption,
            reset_encryption_instance,
        )

        instance1 = get_memory_encryption()
        reset_encryption_instance()
        instance2 = get_memory_encryption()

        # After reset, should be different instances
        assert instance1 is not instance2
