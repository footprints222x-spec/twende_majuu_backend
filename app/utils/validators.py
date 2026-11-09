"""Hand-rolled input validation: each validator returns a cleaned value or raises FieldError."""
import re
from datetime import date

from app.errors import ValidationError
from app.models.constants import GENDERS

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9\s().-]{5,18}[0-9]$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PASSPORT_RE = re.compile(r"^[A-Z0-9]{5,20}$")

MIN_AGE_YEARS = 18


class FieldError(Exception):
    pass


# ---- primitive validators -----------------------------------------------------
def short_text(max_len, min_len=1):
    def validate(value):
        if not isinstance(value, str):
            raise FieldError("Must be text.")
        value = " ".join(value.split())  # trim + collapse whitespace
        if len(value) < min_len:
            raise FieldError(f"Must be at least {min_len} characters.")
        if len(value) > max_len:
            raise FieldError(f"Must be at most {max_len} characters.")
        return value

    return validate


def long_text(max_len):
    def validate(value):
        if not isinstance(value, str):
            raise FieldError("Must be text.")
        value = value.strip()
        if len(value) > max_len:
            raise FieldError(f"Must be at most {max_len} characters.")
        return value

    return validate


def email(value):
    if not isinstance(value, str):
        raise FieldError("Must be text.")
    value = value.strip().lower()
    if len(value) > 255 or not EMAIL_RE.match(value):
        raise FieldError("Enter a valid email address.")
    return value


def phone(value):
    if not isinstance(value, str):
        raise FieldError("Must be text.")
    value = value.strip()
    if not PHONE_RE.match(value):
        raise FieldError("Enter a valid phone number, e.g. +254712345678.")
    return value


def iso_date(value):
    if not isinstance(value, str) or not DATE_RE.match(value.strip()):
        raise FieldError("Use the format YYYY-MM-DD.")
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise FieldError("Not a valid calendar date.")


def date_of_birth(value):
    dob = iso_date(value)
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < MIN_AGE_YEARS:
        raise FieldError(f"Applicants must be at least {MIN_AGE_YEARS} years old.")
    if age > 80:
        raise FieldError("Enter a valid date of birth.")
    return dob


def passport_expiry(value):
    expiry = iso_date(value)
    today = date.today()
    if expiry < today:
        raise FieldError("The passport has already expired.")
    if expiry.year > today.year + 20:
        raise FieldError("Enter a valid passport expiry date.")
    return expiry


def gender(value):
    if not isinstance(value, str):
        raise FieldError("Must be text.")
    candidate = value.strip().lower().replace("-", "_").replace(" ", "_")
    if candidate not in GENDERS:
        raise FieldError(f"Must be one of: {', '.join(GENDERS)}.")
    return candidate


def passport_number(value):
    if not isinstance(value, str):
        raise FieldError("Must be text.")
    cleaned = re.sub(r"[\s-]", "", value).upper()
    if not PASSPORT_RE.match(cleaned):
        raise FieldError("Must be 5-20 letters or digits.")
    return cleaned


def years_experience(value):
    if isinstance(value, bool):
        raise FieldError("Must be a whole number.")
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if not isinstance(value, int):
        raise FieldError("Must be a whole number.")
    if not 0 <= value <= 60:
        raise FieldError("Must be between 0 and 60.")
    return value


def password(value):
    if not isinstance(value, str):
        raise FieldError("Must be text.")
    if len(value) < 8:
        raise FieldError("Must be at least 8 characters.")
    if len(value) > 128:
        raise FieldError("Must be at most 128 characters.")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise FieldError("Must contain at least one letter and one number.")
    return value


# ---- profile payloads ---------------------------------------------------------
PROFILE_FIELDS = {
    "first_name": short_text(100),
    "last_name": short_text(100),
    "phone": phone,
    "date_of_birth": date_of_birth,
    "gender": gender,
    "nationality": short_text(100),
    "country_of_residence": short_text(100),
    "address": long_text(500),
    "passport_number": passport_number,
    "passport_expiry": passport_expiry,
    "position_applied": short_text(100),
    "years_experience": years_experience,
    "biography": long_text(2000),
}
REQUIRED_NAMES = ("first_name", "last_name")


def _is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def validate_profile(data, *, creating=False):
    """Validate any subset of profile fields.

    Unknown keys are ignored (no mass assignment). Optional fields may be cleared
    by sending null or "". First/last name can never be cleared; when creating
    they are mandatory.
    """
    errors, cleaned = {}, {}
    for name, validator in PROFILE_FIELDS.items():
        if name not in data:
            if creating and name in REQUIRED_NAMES:
                errors[name] = "This field is required."
            continue
        value = data[name]
        if _is_blank(value):
            if name in REQUIRED_NAMES:
                errors[name] = "This field is required."
            else:
                cleaned[name] = None
            continue
        try:
            cleaned[name] = validator(value)
        except FieldError as exc:
            errors[name] = str(exc)
    if errors:
        raise ValidationError(errors)
    return cleaned


def validate_fields(data, spec):
    """Validate required fields given as {name: validator}. Returns cleaned dict."""
    errors, cleaned = {}, {}
    for name, validator in spec.items():
        value = data.get(name)
        if _is_blank(value):
            errors[name] = "This field is required."
            continue
        try:
            cleaned[name] = validator(value)
        except FieldError as exc:
            errors[name] = str(exc)
    if errors:
        raise ValidationError(errors)
    return cleaned


def escape_like(term):
    """Escape LIKE wildcards in user-supplied search text (use with escape='\\')."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
