"""Django validator hook: the existing composition policy supplements stock validators."""

from django.core.exceptions import ValidationError


class PasswordCompositionValidator:
    def validate(self, password, user=None):
        if not (
            any(char.isupper() for char in password)
            and any(char.islower() for char in password)
            and any(char.isdigit() for char in password)
            and any(not char.isalnum() for char in password)
        ):
            raise ValidationError(self.get_help_text(), code="password_composition")

    def get_help_text(self):
        return "Password must contain uppercase and lowercase letters, a number, and a symbol."
