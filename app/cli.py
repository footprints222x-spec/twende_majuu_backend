"""Flask CLI commands: `flask create-admin` and `flask purge-expired-tokens`."""
from datetime import datetime, timezone

import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy.exc import IntegrityError

from app.errors import ValidationError
from app.extensions import db
from app.models import Admin, TokenBlocklist, User
from app.models.constants import ROLE_ADMIN
from app.utils import validators as v


@click.command("create-admin")
@click.option("--email", prompt=True, help="Login email for the administrator.")
@click.option("--full-name", prompt="Full name", help="Administrator's display name.")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Password (min 8 chars, letters and numbers). Prompted securely if omitted.",
)
@with_appcontext
def create_admin(email, full_name, password):
    """Create an administrator account."""
    try:
        cleaned = v.validate_fields(
            {"email": email, "full_name": full_name, "password": password},
            {"email": v.email, "full_name": v.short_text(200), "password": v.password},
        )
    except ValidationError as exc:
        raise click.ClickException("; ".join(f"{k}: {msg}" for k, msg in exc.details.items()))

    if User.query.filter_by(email=cleaned["email"]).first():
        raise click.ClickException(f"A user with the email {cleaned['email']} already exists.")

    user = User(email=cleaned["email"], role=ROLE_ADMIN)
    user.set_password(cleaned["password"])
    Admin(user=user, full_name=cleaned["full_name"])
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise click.ClickException("Could not create the administrator (duplicate email).")
    click.echo(f"Administrator created: {cleaned['email']}")


@click.command("purge-expired-tokens")
@with_appcontext
def purge_expired_tokens():
    """Delete revoked-token rows whose tokens have expired anyway."""
    deleted = TokenBlocklist.query.filter(TokenBlocklist.expires_at < datetime.now(timezone.utc)).delete()
    db.session.commit()
    click.echo(f"Removed {deleted} expired token record(s).")


def register_cli(app):
    app.cli.add_command(create_admin)
    app.cli.add_command(purge_expired_tokens)
