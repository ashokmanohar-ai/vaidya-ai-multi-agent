"""Password hashing and constant-time verification, no demo credentials."""
import hashlib
import hmac
import secrets

ITERATIONS = 600_000

def create_hash(password: str) -> str:
    if not isinstance(password,str) or len(password)<14:
        raise ValueError('A password of at least 14 characters is required')
    salt=secrets.token_bytes(24)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}'

def verify_hash(password: str, stored: str) -> bool:
    try:
        _,iters,salt,digest = stored.split('$')
        cost=int(iters)
        if cost<200000 or cost>1500000: return False
        computed=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),cost)
        return hmac.compare_digest(computed,bytes.fromhex(digest))
    except (ValueError,AttributeError,TypeError):
        return False
