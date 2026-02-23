"""A well-structured authentication module for testing CodeSieve."""


def validate_email(email: str) -> bool:
    """Check if an email address has valid format."""
    if "@" not in email:
        return False
    local, domain = email.rsplit("@", 1)
    return bool(local) and "." in domain


def hash_password(password: str, salt: str) -> str:
    """Create a salted hash of a password."""
    import hashlib
    combined = f"{salt}{password}"
    return hashlib.sha256(combined.encode()).hexdigest()


def create_user(username: str, email: str, password: str) -> dict:
    """Create a new user record."""
    if not validate_email(email):
        raise ValueError("Invalid email address")

    salt = "random_salt_here"
    password_hash = hash_password(password, salt)

    return {
        "username": username,
        "email": email,
        "password_hash": password_hash,
        "salt": salt,
        "active": True,
    }


class UserRepository:
    """Handles user data persistence."""

    def __init__(self, database):
        """Initialize with a database connection."""
        self.database = database

    def find_by_email(self, email: str):
        """Look up a user by email address."""
        return self.database.query("users", {"email": email})

    def save(self, user: dict) -> bool:
        """Persist a user record."""
        return self.database.insert("users", user)

    def delete(self, user_id: int) -> bool:
        """Remove a user by ID."""
        return self.database.delete("users", user_id)


def safe_divide(numerator: float, denominator: float) -> float:
    """Divide two numbers with proper error handling."""
    try:
        result = numerator / denominator
    except ZeroDivisionError:
        return 0.0
    return result


def parse_config(filepath: str) -> dict:
    """Parse a configuration file with specific error handling."""
    try:
        with open(filepath) as config_file:
            import json
            return json.load(config_file)
    except FileNotFoundError:
        return {"error": "file not found"}
    except ValueError as exc:
        raise ValueError(f"Invalid config format: {exc}") from exc


def check_age(age: int) -> str:
    """Check if age is valid — uses guard clause pattern."""
    if age < 0:
        return "invalid"
    if age < 18:
        return "minor"
    return "adult"
