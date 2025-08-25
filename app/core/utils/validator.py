import re

class UserValidator:
    @staticmethod
    def validate_email(email: str):
        pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        if not pattern.match(email):
            raise ValueError("Неверный формат email")

    @staticmethod
    def validate_password(password: str):
        if len(password) < 8:
            raise ValueError("Пароль должен быть не меньше 8 символов")
