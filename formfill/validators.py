"""Validation and normalisation of user-provided values.

A validator receives the raw value, all values collected so far and the field key.
It returns ``(normalised_value, warning)`` or raises :class:`ValidationError` with a
message that is shown to the user (in Slovak). Warnings do not block the value but are
reported back so the user can double-check (e.g. a suspicious rodné číslo).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any, Callable


class ValidationError(ValueError):
    pass


Result = tuple[Any, str | None]
Validator = Callable[[Any, dict, str], Result]

REGISTRY: dict[str, Validator] = {}


def validator(name: str):
    def deco(fn: Validator) -> Validator:
        REGISTRY[name] = fn
        return fn

    return deco


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def loose(text: str) -> str:
    """Case- and diacritics-insensitive comparison key."""
    return re.sub(r"\s+", " ", strip_accents(str(text)).casefold()).strip()


def _text(value: Any) -> str:
    if value is None:
        raise ValidationError("Hodnota chýba.")
    return str(value).strip()


def parse_date(value: Any) -> date:
    text = _text(value)
    m = re.fullmatch(r"(\d{1,2})\s*[.\-/ ]\s*(\d{1,2})\s*[.\-/ ]\s*(\d{4})", text)
    if m:
        d, mo, y = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
        if not m:
            raise ValidationError(f"„{text}“ nie je platný dátum. Použite formát DD.MM.RRRR.")
        y, mo, d = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError as exc:
        raise ValidationError(f"„{text}“ nie je platný dátum.") from exc


@validator("date")
def v_date(value, values, key) -> Result:
    return parse_date(value).strftime("%d.%m.%Y"), None


@validator("birth_date")
def v_birth_date(value, values, key) -> Result:
    d = parse_date(value)
    today = date.today()
    if d >= today or d.year < 1920:
        raise ValidationError("Dátum narodenia nie je reálny.")
    age = (today - d).days // 365
    warning = f"Podľa dátumu narodenia máte {age} rokov – skontrolujte ho prosím." if age < 14 else None
    return d.strftime("%d.%m.%Y"), warning


@validator("month_year")
def v_month_year(value, values, key) -> Result:
    text = _text(value)
    m = re.fullmatch(r"(\d{1,2})\s*[./\-]\s*(\d{4})", text)
    if not m:
        raise ValidationError("Zadajte mesiac a rok vo formáte MM/RRRR (napr. 09/2016).")
    month, year = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        raise ValidationError("Mesiac musí byť v rozsahu 1 až 12.")
    return f"{month:02d}/{year}", None


@validator("year")
def v_year(value, values, key) -> Result:
    text = _text(value)
    if not re.fullmatch(r"\d{4}", text) or not 1950 <= int(text) <= date.today().year + 5:
        raise ValidationError("Zadajte rok ako štvorciferné číslo (napr. 2027).")
    return text, None


@validator("academic_year")
def v_academic_year(value, values, key) -> Result:
    text = re.sub(r"\s", "", _text(value))
    m = re.fullmatch(r"(?:20)?(\d{2})(?:/(?:20)?(\d{2}))?", text)
    if not m:
        raise ValidationError("Akademický rok zadajte v tvare 2027/2028.")
    first = int(m.group(1))
    second = int(m.group(2)) if m.group(2) else first + 1
    if second != first + 1:
        raise ValidationError("Akademický rok musí pokrývať dva po sebe idúce roky, napr. 2027/2028.")
    return f"20{first:02d}/20{second:02d}", None


@validator("email")
def v_email(value, values, key) -> Result:
    text = _text(value).lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", text):
        raise ValidationError(f"„{text}“ nie je platná e-mailová adresa.")
    return text, None


@validator("phone")
def v_phone(value, values, key) -> Result:
    text = re.sub(r"[\s\-/()]", "", _text(value))
    if not re.fullmatch(r"\+?\d{9,15}", text):
        raise ValidationError("Telefónne číslo má obsahovať 9 až 15 číslic (napr. +421 900 123 456).")
    if text.startswith("+421") and len(text) == 13:
        return f"+421 {text[4:7]} {text[7:10]} {text[10:]}", None
    if text.startswith("09") and len(text) == 10:
        return f"{text[:4]} {text[4:7]} {text[7:]}", None
    return text, None


SLOVAKIA = {"slovensko", "slovenska republika", "sr", "slovakia", "slovak republic"}


def _is_slovakia(country: Any) -> bool:
    return country is None or loose(country) in SLOVAKIA


@validator("zip")
def v_zip(value, values, key) -> Result:
    text = _text(value)
    country = values.get(key.replace("_zip", "_country"))
    if _is_slovakia(country):
        digits = re.sub(r"\s", "", text)
        if not re.fullmatch(r"\d{5}", digits):
            raise ValidationError("Slovenské PSČ má 5 číslic (napr. 811 08).")
        return f"{digits[:3]} {digits[3:]}", None
    return text.upper(), None


@validator("rodne_cislo")
def v_rodne_cislo(value, values, key) -> Result:
    digits = re.sub(r"[\s/]", "", _text(value))
    if not re.fullmatch(r"\d{9,10}", digits):
        raise ValidationError("Rodné číslo má tvar RRMMDD/XXXX (9 alebo 10 číslic).")
    warnings = []
    yy, mm, dd = int(digits[:2]), int(digits[2:4]), int(digits[4:6])
    female = mm > 50
    month = mm - 50 if female else mm
    if month > 20:  # +20 / +70 variant used when a day's numbers run out
        month -= 20
    if not (1 <= month <= 12 and 1 <= dd <= 31):
        raise ValidationError("Prvá časť rodného čísla neobsahuje platný dátum narodenia (RRMMDD).")
    if len(digits) == 10 and int(digits) % 11 != 0 and not (int(digits[:9]) % 11 == 10 and digits[9] == "0"):
        warnings.append("kontrolná číslica nesedí (číslo nie je deliteľné 11)")
    birth = values.get("birth_date")
    if birth:
        try:
            b = parse_date(birth)
            if (b.year % 100, b.month, b.day) != (yy, month, dd):
                warnings.append("nezhoduje sa s dátumom narodenia")
        except ValidationError:
            pass
    gender = values.get("gender")
    if gender and (loose(gender) == "zena") != female:
        warnings.append("mesiac v rodnom čísle nezodpovedá pohlaviu (ženy majú +50)")
    warning = f"Rodné číslo: {', '.join(warnings)}. Prosím, overte ho." if warnings else None
    return f"{digits[:6]}/{digits[6:]}", warning


@validator("school_code")
def v_school_code(value, values, key) -> Result:
    digits = re.sub(r"\s", "", _text(value))
    if not re.fullmatch(r"\d{1,9}", digits):
        raise ValidationError("Kód strednej školy tvoria len číslice (najviac 9).")
    # Note 10 of the form: shorter codes are padded with leading zeros to 9 digits.
    return digits.zfill(9), None


@validator("field_code")
def v_field_code(value, values, key) -> Result:
    code = re.sub(r"[\s\-]", "", _text(value)).upper()
    # Note 12: a five-digit code (odbor without zameranie) is completed with "00".
    if re.fullmatch(r"\d{4}[A-Z]", code) or re.fullmatch(r"\d{5}", code):
        code += "00"
    if not re.fullmatch(r"\d{4}[A-Z0-9]\d{2}", code):
        raise ValidationError("Kód študijného odboru má 7 znakov, napr. 7902J00 alebo 2561M00.")
    return code, None


@validator("decimal2")
def v_decimal2(value, values, key) -> Result:
    text = _text(value).replace(",", ".")
    try:
        number = float(text)
    except ValueError as exc:
        raise ValidationError(f"„{value}“ nie je číslo.") from exc
    if not 1 <= number <= 5:
        raise ValidationError("Priemer musí byť medzi 1,00 a 5,00.")
    return f"{number:.2f}".replace(".", ","), None


@validator("averages")
def v_averages(value, values, key) -> Result:
    items = value if isinstance(value, list) else re.split(r"[;\s]+", _text(value))
    return [v_decimal2(i, values, key)[0] for i in items if str(i).strip()], None


@validator("grades_table")
def v_grades_table(value, values, key) -> Result:
    rows = _rows(value)
    for row in rows:
        for grade in row[1:]:
            if grade and not re.fullmatch(r"[1-5]|[A-Fa-f]", grade):
                raise ValidationError(f"Známka „{grade}“ ({row[0]}) musí byť 1 až 5.")
    return rows, None


@validator("table")
def v_table(value, values, key) -> Result:
    return _rows(value), None


def _rows(value: Any) -> list[list[str]]:
    if isinstance(value, str):
        value = [re.split(r"\s*[;|]\s*|\t", line) for line in value.splitlines() if line.strip()]
    if not isinstance(value, list) or not all(isinstance(r, (list, tuple)) for r in value):
        raise ValidationError("Tabuľku zadajte po riadkoch, napr. „Matematika: 1, 2, 1“.")
    return [[str(c).strip() if c is not None else "" for c in row] for row in value]


def run_validator(name: str | None, value: Any, values: dict, key: str) -> Result:
    if not name:
        return value, None
    return REGISTRY[name](value, values, key)
