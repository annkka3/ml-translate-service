import bcrypt

class PasswordHasher:
    @staticmethod
    def hash(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def check(password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode(), hashed.encode())
