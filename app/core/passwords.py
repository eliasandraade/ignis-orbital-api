"""Password policy for accounts created or changed through the API.

The demo seed (seed/seed_users.py) writes users directly and is restricted to
development/test/demo environments; its published passwords are also rejected
here so they can never be set on an account through the admin API.
"""

MIN_PASSWORD_LENGTH = 12
# bcrypt only uses the first 72 bytes; longer input would be silently truncated.
MAX_PASSWORD_BYTES = 72

PUBLISHED_PASSWORDS = frozenset(
    {
        "admin@123",
        "gestor@123",
        "operador@123",
        "campo@123",
        "ignis_secret",
        "password",
        "12345678",
        "123456789012",
    }
)


def validate_new_password(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"A senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"A senha deve ter no máximo {MAX_PASSWORD_BYTES} bytes.")
    if value.lower() in PUBLISHED_PASSWORDS:
        raise ValueError("Senha publicada/demonstrativa não é permitida.")
    return value
