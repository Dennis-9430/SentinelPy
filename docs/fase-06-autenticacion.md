# Fase 06: Autenticación de Analistas

## Objetivo

Proteger el dashboard de SentinelPy con autenticación mediante JWT en
cookie httpOnly, con roles de usuario y seed automático del admin inicial.
Sin autenticación, cualquiera con acceso a la URL del dashboard podía
ver y modificar alertas y reglas — un riesgo de seguridad inaceptable.

## Arquitectura

```
                    ┌──────────────────────────────────────┐
                    │           Navegador Web              │
                    │                                      │
                    │  POST /login (form)                  │
                    │  ← cookie: access_token (JWT)        │
                    │                                      │
                    │  GET /events /alerts /rules          │
                    │  → cookie: access_token (automática) │
                    │                                      │
                    │  POST /api/auth/logout               │
                    │  ← cookie eliminada + redirect /login│
                    └──────────┬───────────────────────────┘
                               │
                    ┌──────────▼───────────────────────────┐
                    │           FastAPI App                 │
                    │                                      │
                    │  ┌────────────────────────────┐      │
                    │  │  get_current_user_from_cookie  │   │
                    │  │  ─── Lee cookie access_token │   │
                    │  │  ─── Decodifica JWT          │   │
                    │  │  ─── Busca User en BD       │   │
                    │  │  ─── Devuelve User o None    │   │
                    │  └──────────┬─────────────────┘      │
                    │             │                         │
                    │  ┌──────────▼─────────────────┐      │
                    │  │  ¿User autenticado?        │      │
                    │  │  ├── Sí → renderiza página │      │
                    │  │  └── No → redirect /login  │      │
                    │  └────────────────────────────┘      │
                    │                                      │
                    │  ┌────────────────────────────┐      │
                    │  │  AuthService                │      │
                    │  │  ─── bcrypt hash/verify    │      │
                    │  │  ─── JWT create/decode     │      │
                    │  │  ─── crear_usuario()       │      │
                    │  │  ─── autenticar()          │      │
                    │  └────────────────────────────┘      │
                    └──────────────────────────────────────┘
```

## Componentes Nuevos

### 1. Modelo User

```python
class User(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "users"

    username:       str   # único, indexado, min 3 chars
    hashed_password: str   # bcrypt (passlib)
    role:           str   # admin | analyst
    active:         bool  # false = deshabilitado
```

- UUID como primary key (consistente con el resto del proyecto)
- Timestamps `created_at` / `updated_at` automáticos (TimestampMixin)
- Username en minúsculas, normalizado al crear

### 2. AuthService

**Password hashing con bcrypt:**

```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

**JWT con PyJWT:**

```python
import jwt

def crear_token(self, user: User) -> str:
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        ),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

@staticmethod
def decodificar_token(token: str, secret_key: str) -> dict | None:
    try:
        return jwt.decode(token, secret_key, algorithms=[settings.jwt_algorithm])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
```

### 3. Cookie httpOnly

La cookie se setea en el response del login y se elimina en logout:

| Propiedad | Valor | Por qué |
|-----------|-------|---------|
| `httponly` | `True` | No accesible desde JavaScript (mitiga XSS) |
| `samesite` | `lax` | Previene CSRF, permite navegación GET |
| `max_age` | 8 horas | Duración de sesión configurable |
| `secure` | no (dev) | En producción debe ser `True` (HTTPS) |

### 4. Dependencia de Autenticación

```python
async def get_current_user_from_cookie(request: Request, session: AsyncSession):
    token = request.cookies.get("access_token")
    if not token:
        return None

    payload = AuthService.decodificar_token(token, settings.secret_key)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    return await AuthService(session).obtener_por_id(UUID(user_id))
```

Cada ruta HTML verifica al inicio:
```python
user = await get_current_user_from_cookie(request, session)
if not user:
    return RedirectResponse(url="/login", status_code=303)
```

### 5. Seed de Admin Automático

En el `lifespan` de la aplicación, después de crear las tablas:

```python
async with db_session() as seed_session:
    auth_svc = AuthService(seed_session)
    try:
        admin_user = await auth_svc.crear_usuario(
            username=settings.admin_username,
            password=settings.admin_password,
            role="admin",
        )
        logger.info("Admin creado: %s", admin_user.username)
    except ValueError:
        logger.info("Admin ya existe, omitiendo seed")
```

Credenciales por defecto (configurables vía .env):

| Variable | Default |
|----------|---------|
| `admin_username` | `admin` |
| `admin_password` | `admin123` |

## Flujo Completo

### Login exitoso

1. Usuario ingresa usuario/contraseña en `/login`
2. POST a `/login` (form HTML) o `/api/auth/login` (JSON)
3. `AuthService.autenticar()` busca user por username, verifica bcrypt
4. Si OK → `AuthService.crear_token()` genera JWT
5. Se setea cookie `access_token` en el response
6. Redirect a `/` (form) o `{"mensaje": "Login exitoso"}` (API)

### Acceso a ruta protegida

1. Browser envía request con cookie `access_token`
2. `get_current_user_from_cookie()` extrae y decodifica JWT
3. Busca User en BD por el UUID del payload
4. Si existe → pasa `user` al template
5. Si no → `RedirectResponse(url="/login")`

### Logout

1. POST a `/api/auth/logout` (desde form en navbar o API)
2. Se crea `RedirectResponse(url="/login")`
3. Se llama `response.delete_cookie("access_token")`
4. El browser recibe el redirect sin la cookie

## Endpoints

### HTML (server-side rendering)

| Método | Ruta | Protegido | Descripción |
|--------|------|-----------|-------------|
| GET | `/login` | No | Página de login minimalista |
| POST | `/login` | No | Login desde formulario HTML |

### API REST

| Método | Ruta | Protegido | Descripción |
|--------|------|-----------|-------------|
| POST | `/api/auth/login` | No | Login JSON (devuelve token en cookie) |
| POST | `/api/auth/logout` | No | Logout + redirect |
| GET | `/api/auth/me` | Sí | Datos del usuario autenticado |

### Rutas Protegidas

Todas las rutas HTML del dashboard verifican auth:

| Ruta | Método | Sin auth |
|------|--------|----------|
| `/` | GET | → redirect /login |
| `/events` | GET | → redirect /login |
| `/alerts` | GET | → redirect /login |
| `/rules` | GET | → redirect /login |
| `/alerts/{id}/estado` | POST | → redirect /login |
| `/rules/{id}/toggle` | POST | → redirect /login |

## Archivos Creados/Modificados

| Archivo | Acción | Descripción |
|---------|--------|-------------|
| `backend/app/models/user.py` | Creado | Modelo User (username, hashed_password, role, active) |
| `backend/app/schemas/user.py` | Creado | UserCreate, UserLogin, UserRead |
| `backend/app/services/auth_service.py` | Creado | AuthService con bcrypt + JWT |
| `backend/app/auth.py` | Creado | Dependencias get_current_user_from_cookie |
| `backend/app/api/auth.py` | Creado | Endpoints /api/auth/login, logout, me |
| `backend/app/templates/login.html` | Creado | Login minimalista dark mode |
| `backend/app/main.py` | Modificado | +60 líneas: router auth, login GET/POST, seed admin, protección rutas |
| `backend/app/templates/base.html` | Modificado | Navbar con username + botón Salir |
| `backend/app/config.py` | Modificado | jwt_algorithm, admin_username, admin_password |
| `backend/requirements.txt` | Modificado | passlib[bcrypt], bcrypt, PyJWT |
| `backend/app/models/__init__.py` | Modificado | Import de User |
| `backend/app/schemas/__init__.py` | Modificado | Import de schemas de usuario |
| `backend/alembic/versions/002_crear_tabla_usuarios.py` | Creado | Migración tabla users |
| `backend/tests/test_auth.py` | Creado | 16 tests de autenticación |

## Tests (16 tests)

| Test | Tipo | Qué verifica |
|------|------|-------------|
| `test_crear_usuario` | Unitario | Creación de usuario con bcrypt |
| `test_autenticar_correcto` | Unitario | Login con credenciales válidas |
| `test_autenticar_password_incorrecto` | Unitario | Login con password incorrecta → None |
| `test_autenticar_usuario_inexistente` | Unitario | Login con usuario que no existe → None |
| `test_autenticar_usuario_inactivo` | Unitario | Usuario deshabilitado no puede loguearse |
| `test_crear_token` | Unitario | Generación de JWT válido |
| `test_decodificar_token_valido` | Unitario | Decodificación de JWT correcto |
| `test_decodificar_token_invalido` | Unitario | Token inválido → None |
| `test_usuario_duplicado_raise` | Unitario | Username duplicado lanza ValueError |
| `test_hash_password_verification` | Unitario | hash + verify funcionan en conjunto |
| `test_health_check` | Integración | GET /health funciona sin auth |
| `test_login_page_render` | Integración | GET /login renderiza HTML |
| `test_dashboard_redirect_when_not_authenticated` | Integración | GET / → redirect /login |
| `test_events_redirect_when_not_authenticated` | Integración | GET /events → redirect /login |
| `test_alerts_redirect_when_not_authenticated` | Integración | GET /alerts → redirect /login |
| `test_rules_redirect_when_not_authenticated` | Integración | GET /rules → redirect /login |

## Lecciones Aprendidas

### 1. Cookie httpOnly + JWT es el approach correcto para SSR

Alternativas consideradas:
- **Session server-side** (con Redis): potente pero agrega otra dependencia
- **JWT en header Authorization**: ideal para APIs, no funciona con SSR
- **JWT en cookie httpOnly**: lo mejor de ambos — el token viaja automáticamente
  en cada request, no es accesible desde JS, no necesita storage server-side

Para un SIEM de PyME sin Redis, cookie httpOnly + JWT es la combinación
perfecta: simple, segura, sin infraestructura extra.

### 2. Depends no funciona en rutas HTML

FastAPI `Depends()` funciona en rutas con `response_model` pero no en
rutas que devuelven `HTMLResponse` directamente porque no hay schema
contra el cual validar el resultado. Por eso las rutas HTML usan
`obtener_session()` como async generator en lugar de `Depends(get_session)`.

La dependencia de auth sigue el mismo patrón — se llama manualmente al
inicio de cada ruta, no como un `Depends`.

### 3. Passlib + bcrypt sigue siendo el gold standard

`passlib` abstrae el versionado de bcrypt y maneja la detección de
esquemas automáticamente. Al hacer `verify_password()`, detecta qué
algoritmo se usó para hashear (incluso si cambiamos de bcrypt a otra cosa
en el futuro). Esto permite hacer upgrades graduales de hash.

### 4. El seed de admin en lifespan con try/except es limpio

En lugar de hacer un `if user.exists()` antes de crear, simplemente
intentamos crear y capturamos `ValueError` si el usuario ya existe.
Esto evita una race condition (el check + create nunca es atómico sin
transacción) y mantiene el código simple.

### 5. Logout con redirect, no JSON

El endpoint de logout original devolvía JSON `{"mensaje": "Sesión cerrada"}`.
El problema: el form HTML de "Salir" POSTea a ese endpoint, y el navegador
mostraba el JSON como página. La solución fue cambiar el endpoint a
`RedirectResponse(url="/login")` con la cookie eliminada en el mismo response.

Para API clients el comportamiento es igual de correcto — siguen el redirect
sin problemas. No hay razón para que un logout devuelva JSON cuando un
redirect es más útil.

### 6. PyJWT y la advertencia de clave corta

Con la `secret_key` por defecto ("change-me-in-production", 23 bytes),
PyJWT emite `InsecureKeyLengthWarning` porque SHA256 requiere mínimo 32
bytes (256 bits). En desarrollo no es un problema, pero en producción
hay que generar una clave con:

```powershell
# PowerShell
[System.Convert]::ToHexString((1..32 | ForEach-Object { Get-Random -Max 256 }))
```

O en Linux/macOS:
```bash
openssl rand -hex 32
```

## Próximos Pasos (Fase 07)

- **Notificaciones por email** (SMTP para alertas críticas)
- **Sistema de permisos por rol** (admin puede todo, analyst solo lectura)
- **API Key** para integraciones externas sin cookie
- **2FA / TOTP** para cuentas admin (producción)
