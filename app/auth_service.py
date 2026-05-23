from .database import get_connection


class AuthService:
    # Logical microservice: AuthService.

    # Rubric/design link:
    # - Validates client node credentials against the server-hosted SQLite DB.
    # - Keeps authentication logic separate from routing and shared file access.

    def validate_user(self, username: str, password: str) -> bool:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT username FROM users WHERE username = ? AND password = ?",
                (username, password),
            ).fetchone()
        return row is not None


auth_service = AuthService()
