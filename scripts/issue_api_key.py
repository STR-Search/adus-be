#!/usr/bin/env python3
"""Mint an API key for an existing user and print the plaintext once.

The plaintext key is shown ONLY here — it is stored hashed, so copy it now.
Hand the printed key to the consuming team; they authenticate by sending it in
the ``X-ADUS-API-KEY`` header on every request.

Usage:
    uv run python scripts/issue_api_key.py --user-id 42 --name "team-x cli"
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.users.repositories.api_key_repository import ApiKeyRepository
from app.users.repositories.user_repository import UserRepository
from app.users.services.api_key_service import ApiKeyService


async def issue(*, user_id: int, name: str, session_factory=AsyncSessionLocal) -> None:
    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            sys.exit(f"No active user with id={user_id}")

        service = ApiKeyService(ApiKeyRepository(session), user_repo)
        api_key, raw_key = await service.create_key(user_id=user_id, name=name)

    print("API key created — copy it now, it will NOT be shown again:\n")
    print(f"  id:      {api_key.id}")
    print(f"  user_id: {api_key.user_id}")
    print(f"  name:    {api_key.name}")
    print(f"  prefix:  {api_key.prefix}")
    print(f"\n  X-ADUS-API-KEY: {raw_key}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue an API key for a user.")
    parser.add_argument("--user-id", type=int, required=True, help="Owning user id")
    parser.add_argument(
        "--name", required=True, help="Human-readable label for the key"
    )
    args = parser.parse_args()
    asyncio.run(issue(user_id=args.user_id, name=args.name))


if __name__ == "__main__":
    main()
