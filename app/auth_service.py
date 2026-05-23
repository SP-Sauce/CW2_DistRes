from .database import get_connection


# Logical microservice that validates client credentials against SQLite.
class AuthService:
    # Checks whether a username and password match a stored user record.
    def validate_user(self, username: str, password: str) -> bool:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT username FROM users WHERE username = ? AND password = ?",
                (username, password),
            ).fetchone()
        return row is not None


auth_service = AuthService()
