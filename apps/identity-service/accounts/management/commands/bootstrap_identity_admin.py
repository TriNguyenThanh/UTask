import getpass

from allauth.account.models import EmailAddress
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from accounts.managers import UserManager
from accounts.models import User


class Command(BaseCommand):
    help = "Interactively create a global SYSTEM_ADMIN account."

    def add_arguments(self, parser):
        parser.add_argument("--email")
        parser.add_argument("--username")
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")

    def handle(self, *args, **options):
        email = options["email"] or input("Email: ").strip()
        username = options["username"]
        if username is None:
            username = input("Username (leave blank to derive from email): ").strip() or None

        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise CommandError("The password entries did not match.")
        try:
            validate_password(password, user=User(email=email, username=username or ""))
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error

        normalized_email = UserManager.normalize_email(email)
        if User.objects.filter(email=normalized_email).exists():
            raise CommandError("That email already belongs to an account.")
        normalized_username = UserManager.normalize_username(username)
        if normalized_username and User.objects.filter(username=normalized_username).exists():
            raise CommandError("That username already belongs to an account.")

        try:
            with transaction.atomic():
                user = User.objects.create_superuser(
                    email=email,
                    password=password,
                    username=username,
                    first_name=options["first_name"],
                    last_name=options["last_name"],
                )
                # Explicit local bootstrap trusts the operator,
                # never a public client role/staff flag.
                EmailAddress.objects.create(
                    user=user, email=user.email, verified=True, primary=True
                )
        except IntegrityError as error:
            raise CommandError(
                "Identity changed during bootstrap; retry with unused credentials."
            ) from error

        self.stdout.write(self.style.SUCCESS(f"Created SYSTEM_ADMIN account {user.email}."))
