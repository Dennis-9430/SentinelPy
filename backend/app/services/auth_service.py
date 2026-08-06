"""Authentication service: create users, validate credentials, JWT."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

# passlib context with bcrypt — we cache hashes for performance
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Handles registration, authentication and JWT tokens."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Password hashing ──────────────────────────────────────────────────

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password with bcrypt."""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain, hashed)

    # ── User CRUD ────────────────────────────────────────────────────────

    async def crear_usuario(
        self, username: str, password: str, role: str = "analyst"
    ) -> User:
        """Create a new user with a hashed password.

        Normalizes the username to lowercase without spaces. If the user
        already exists, raises ValueError.

        Args:
            username: Unique username.
            password: Plain text password (hashed before saving).
            role: User role (admin | analyst).

        Returns:
            The created User instance.

        Raises:
            ValueError: If the username is already registered.
        """
        username = username.strip().lower()

        existe = await self.session.execute(
            select(User).where(User.username == username)
        )
        if existe.scalar_one_or_none():
            raise ValueError(f"User '{username}' already exists")

        user = User(
            username=username,
            hashed_password=self.hash_password(password),
            role=role,
            active=True,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        logger.info("User created: %s (%s)", user.username, user.role)
        return user

    async def autenticar(self, username: str, password: str) -> User | None:
        """Validate credentials and return the User if they are correct.

        Verifies that the user exists, is active, and the password
        matches the stored hash.

        Args:
            username: Username.
            password: Plain text password.

        Returns:
            User if the credentials are valid, None otherwise.
        """
        username = username.strip().lower()
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()

        if not user:
            return None
        if not user.active:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None

        return user

    async def obtener_por_id(self, user_id: UUID) -> User | None:
        """Get a user by their UUID."""
        return await self.session.get(User, user_id)

    # ── JWT ──────────────────────────────────────────────────────────────

    def crear_token(self, user: User) -> str:
        """Create a JWT with the user's identity.

        The token includes: id (sub), username, role, and expiration.
        It is signed with the configured secret_key and algorithm.

        Args:
            user: User instance to encode in the token.

        Returns:
            String with the signed JWT.
        """
        expira = datetime.now(UTC) + timedelta(
            minutes=settings.access_token_expire_minutes
        )
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "exp": expira,
        }
        token = jwt.encode(
            payload, settings.secret_key, algorithm=settings.jwt_algorithm
        )
        return token

    @staticmethod
    def decodificar_token(token: str, secret_key: str) -> dict | None:
        """Decode and validate a JWT.

        Verifies the token signature and expiration.

        Args:
            token: JWT string.
            secret_key: Secret key to verify the signature.

        Returns:
            Token payload if valid, None if expired or invalid.
        """
        try:
            payload = jwt.decode(token, secret_key, algorithms=[settings.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token: %s", e)
            return None
