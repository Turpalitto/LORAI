from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
from .config import settings
pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
def hash_pw(p: str) -> str: return pwd.hash(p)
def verify_pw(p: str, h: str) -> bool: return pwd.verify(p, h)
def make_token(sub: str, role: str = "doctor") -> str:
    exp = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": sub, "role": role, "exp": exp}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
def decode_token(t: str) -> dict:
    return jwt.decode(t, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
