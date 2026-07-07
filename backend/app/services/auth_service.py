"""Servicio de autenticación: crear usuarios, validar credenciales, JWT."""

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

# Contexto de passlib con bcrypt — cacheamos los hashes para performance
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Maneja registro, autenticación y tokens JWT."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Password hashing ──────────────────────────────────────────────────

    @staticmethod
    def hash_password(password: str) -> str:
        """Hashea una contraseña con bcrypt."""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        """Verifica una contraseña contra su hash."""
        return pwd_context.verify(plain, hashed)

    # ── User CRUD ────────────────────────────────────────────────────────

    async def crear_usuario(
        self, username: str, password: str, role: str = "analyst"
    ) -> User:
        """Crea un nuevo usuario con password hasheada.

        Normaliza el username a minúsculas sin espacios. Si el usuario
        ya existe, lanza ValueError.

        Argumentos:
            username: Nombre de usuario único.
            password: Contraseña en texto plano (se hashea antes de guardar).
            role: Rol del usuario (admin | analyst).

        Retorna:
            La instancia de User creada.

        Raises:
            ValueError: Si el username ya está registrado.
        """
        username = username.strip().lower()

        existe = await self.session.execute(
            select(User).where(User.username == username)
        )
        if existe.scalar_one_or_none():
            raise ValueError(f"El usuario '{username}' ya existe")

        user = User(
            username=username,
            hashed_password=self.hash_password(password),
            role=role,
            active=True,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        logger.info("Usuario creado: %s (%s)", user.username, user.role)
        return user

    async def autenticar(self, username: str, password: str) -> User | None:
        """Valida credenciales y devuelve el User si son correctas.

        Verifica que el usuario exista, esté activo, y la contraseña
        coincida con el hash almacenado.

        Argumentos:
            username: Nombre de usuario.
            password: Contraseña en texto plano.

        Retorna:
            User si las credenciales son válidas, None en caso contrario.
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
        """Obtiene un usuario por su UUID."""
        return await self.session.get(User, user_id)

    # ── JWT ──────────────────────────────────────────────────────────────

    def crear_token(self, user: User) -> str:
        """Crea un JWT con la identidad del usuario.

        El token incluye: id (sub), username, role, y expiración.
        Se firma con la secret_key y el algoritmo configurados.

        Argumentos:
            user: Instancia de User a codificar en el token.

        Retorna:
            String con el JWT firmado.
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
        """Decodifica y valida un JWT.

        Verifica la firma y la expiración del token.

        Argumentos:
            token: JWT string.
            secret_key: Clave secreta para verificar la firma.

        Retorna:
            Payload del token si es válido, None si expiró o es inválido.
        """
        try:
            payload = jwt.decode(token, secret_key, algorithms=[settings.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expirado")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning("Token inválido: %s", e)
            return None
