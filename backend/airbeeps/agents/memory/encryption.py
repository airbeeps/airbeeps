"""
Memory Encryption Utilities.

Provides Fernet-based encryption for memory content at rest.
"""

import base64
import hashlib
import logging
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class MemoryEncryption:
    """
    Handles encryption/decryption of memory content using Fernet.

    Fernet guarantees that data encrypted using it cannot be further
    manipulated or read without the key.
    """

    def __init__(self, encryption_key: bytes | str | None = None):
        """
        Initialize encryption with a key.

        Args:
            encryption_key: Fernet key (32 url-safe base64 bytes) or None to auto-generate
        """
        if encryption_key is None:
            # Try to load from environment
            env_key = os.environ.get("AIRBEEPS_MEMORY_ENCRYPTION_KEY")
            if env_key:
                encryption_key = env_key
            else:
                # Generate a key for development (warn in logs)
                logger.warning(
                    "No AIRBEEPS_MEMORY_ENCRYPTION_KEY set. "
                    "Generating ephemeral key - memories will be lost on restart!"
                )
                encryption_key = Fernet.generate_key()

        if isinstance(encryption_key, str):
            encryption_key = encryption_key.encode()

        # Validate key format
        try:
            self._cipher = Fernet(encryption_key)
        except Exception as e:
            logger.error(f"Invalid encryption key format: {e}")
            raise ValueError(
                "Invalid encryption key. Must be 32 url-safe base64-encoded bytes. "
                "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            ) from e

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext content.

        Args:
            plaintext: Content to encrypt

        Returns:
            Base64-encoded encrypted content
        """
        if not plaintext:
            return plaintext

        encrypted_bytes = self._cipher.encrypt(plaintext.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt encrypted content.

        Args:
            ciphertext: Base64-encoded encrypted content

        Returns:
            Decrypted plaintext

        Raises:
            ValueError: If decryption fails (wrong key or corrupted data)
        """
        if not ciphertext:
            return ciphertext

        try:
            decrypted_bytes = self._cipher.decrypt(ciphertext.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken as e:
            logger.error(
                "Failed to decrypt memory content - invalid key or corrupted data"
            )
            raise ValueError("Failed to decrypt memory content") from e

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new Fernet encryption key.

        Returns:
            Base64-encoded key string
        """
        return Fernet.generate_key().decode("utf-8")

    @staticmethod
    def derive_key_from_secret(secret: str, salt: bytes | None = None) -> str:
        """
        Derive a Fernet key from a secret string (e.g., user's password).

        This allows user-specific encryption if needed.

        Args:
            secret: Secret string to derive key from
            salt: Optional salt bytes (uses default if not provided)

        Returns:
            Base64-encoded Fernet key
        """
        if salt is None:
            salt = b"airbeeps_memory_salt_v1"

        # Use PBKDF2 to derive a key
        import hashlib

        dk = hashlib.pbkdf2_hmac(
            "sha256",
            secret.encode("utf-8"),
            salt,
            iterations=100000,
            dklen=32,
        )
        # Fernet requires url-safe base64 encoding
        return base64.urlsafe_b64encode(dk).decode("utf-8")


# Singleton instance
_encryption_instance: MemoryEncryption | None = None


def get_memory_encryption() -> MemoryEncryption:
    """Get the global memory encryption instance."""
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = MemoryEncryption()
    return _encryption_instance


def reset_encryption_instance() -> None:
    """Reset the global encryption instance (for testing)."""
    global _encryption_instance
    _encryption_instance = None
