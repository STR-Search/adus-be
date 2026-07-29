import hashlib
import secrets

from app.users.models.api_key import ApiKey
from app.users.models.user import User
from app.users.repositories.api_key_repository import ApiKeyRepository
from app.users.repositories.user_repository import UserRepository

# Plaintext keys look like ``adus_sk_<43 url-safe chars>``. The prefix is a
# static, human-recognisable marker; the random suffix carries the entropy.
_KEY_PREFIX = "adus_sk_"
_TOKEN_BYTES = 32  # -> ~43 url-safe chars, ~256 bits of entropy
# How many leading chars of the plaintext we persist for display (never enough
# to reconstruct the key).
_DISPLAY_PREFIX_LEN = 12


class ApiKeyService:
    def __init__(
        self,
        api_key_repository: ApiKeyRepository,
        user_repository: UserRepository,
    ):
        self.api_key_repository = api_key_repository
        self.user_repository = user_repository

    @staticmethod
    def _generate() -> str:
        return f"{_KEY_PREFIX}{secrets.token_urlsafe(_TOKEN_BYTES)}"

    @staticmethod
    def _hash(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    async def create_key(self, *, user_id: int, name: str) -> tuple[ApiKey, str]:
        """Mint a new key. Returns (record, plaintext); plaintext is shown once."""
        raw_key = self._generate()
        api_key = await self.api_key_repository.create(
            user_id=user_id,
            name=name,
            prefix=raw_key[:_DISPLAY_PREFIX_LEN],
            key_hash=self._hash(raw_key),
        )
        return api_key, raw_key

    async def resolve_user(self, raw_key: str) -> User | None:
        """Resolve the owning user for a presented plaintext key, or None.

        Returns None if the key doesn't match an active record or the owning
        user is missing/soft-deleted.
        """
        api_key = await self.api_key_repository.get_active_by_hash(self._hash(raw_key))
        if api_key is None:
            return None
        return await self.user_repository.get_by_id(api_key.user_id)

    async def list_keys(self, user_id: int) -> list[ApiKey]:
        return await self.api_key_repository.list_by_user(user_id)

    async def revoke_key(self, *, api_key_id: int, user_id: int) -> bool:
        """Revoke a key owned by user_id. Returns False if not found/not owned."""
        api_key = await self.api_key_repository.get_by_id_for_user(api_key_id, user_id)
        if api_key is None:
            return False
        await self.api_key_repository.revoke(api_key)
        return True
