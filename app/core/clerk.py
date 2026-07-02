import jwt
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from app.core.config import get_config
from app.core.logger import logger

config = get_config()

# PyJWKClient caches the fetched signing keys, so network I/O only happens on a
# cache miss (first request or key rotation).
_jwks_client = jwt.PyJWKClient(config.CLERK_JWKS_URL) if config.CLERK_JWKS_URL else None


async def verify_clerk_token(token: str) -> dict:
    """Verify a Clerk-issued RS256 JWT and return its claims.

    Raises HTTPException(401) if the token is missing, malformed, or invalid.
    The `sub` claim holds the Clerk user id.
    """
    if _jwks_client is None:
        logger.error("clerk.verify.misconfigured", reason="CLERK_JWKS_URL not set")
        raise HTTPException(status_code=500, detail="Auth not configured")

    try:
        # get_signing_key_from_jwt does blocking network I/O on a cache miss.
        signing_key = await run_in_threadpool(
            _jwks_client.get_signing_key_from_jwt, token
        )
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=config.CLERK_ISSUER,
            # Clerk session tokens carry no `aud` claim by default.
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as e:
        logger.info("clerk.verify.failed", error=str(e))
        raise HTTPException(status_code=401, detail="Invalid or expired token")
