# from passlib.context import CryptContext
# from datetime import datetime, timedelta
# from jose import jwt
# from app.config import settings

# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# def get_password_hash(password: str):
#     password = password[:72]  
#     return pwd_context.hash(password)

# def verify_password(plain_password, hashed_password):
#     plain_password = plain_password[:72] 
#     return pwd_context.verify(plain_password, hashed_password)

# def create_access_token(data: dict, expires_delta: int = None):
#     to_encode = data.copy()
#     expire = datetime.utcnow() + timedelta(minutes=(expires_delta or settings.ACCESS_TOKEN_EXPIRE_MINUTES))
#     to_encode.update({"exp": expire})
#     encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
#     return encoded_jwt


# filepath: f:\2025\PS\projects\adgenius_fastapi_project\app\utils\security.py
import bcrypt
from datetime import datetime, timedelta
import jwt  # Using PyJWT for token handling
from app.config import settings

def get_password_hash(password: str):
    # Truncate the password to 72 characters and hash it
    password = password[:72].encode('utf-8')  # bcrypt requires bytes
    hashed = bcrypt.hashpw(password, bcrypt.gensalt())
    return hashed.decode('utf-8')  # Store the hash as a string

def verify_password(plain_password: str, hashed_password: str):
    # Truncate the password to 72 characters and verify it
    plain_password = plain_password[:72].encode('utf-8')  # bcrypt requires bytes
    hashed_password = hashed_password.encode('utf-8')  # Convert stored hash to bytes
    return bcrypt.checkpw(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: int = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=(expires_delta or settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded_jwt