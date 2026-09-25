import pytest

from formfill.validators import ValidationError, run_validator


def ok(name, value, values=None, key="k"):
    return run_validator(name, value, values or {}, key)


@pytest.mark.parametrize("raw,expected", [("18.4.2008", "18.04.2008"), ("2008-04-18", "18.04.2008"),
                                          ("18. 04. 2008", "18.04.2008")])
def test_date_normalisation(raw, expected):
    assert ok("date", raw)[0] == expected


def test_invalid_date():
    with pytest.raises(ValidationError):
        ok("date", "31.02.2020")


def test_birth_date_in_future_rejected():
    with pytest.raises(ValidationError):
        ok("birth_date", "01.01.2999")


@pytest.mark.parametrize("raw", ["2027/2028", "27/28", "2027", "2027 / 28"])
def test_academic_year(raw):
    assert ok("academic_year", raw)[0] == "2027/2028"


def test_academic_year_must_be_consecutive():
    with pytest.raises(ValidationError):
        ok("academic_year", "2027/2029")


def test_rodne_cislo_valid_and_consistent():
    # 0154010010: female (+50 month), born 01.04.2001, divisible by 11
    value, warning = ok("rodne_cislo", "015401/0010",
                        {"birth_date": "01.04.2001", "gender": "žena"})
    assert value == "015401/0010"
    assert warning is None


def test_rodne_cislo_inconsistent_gives_warning_not_error():
    value, warning = ok("rodne_cislo", "080418 1234", {"birth_date": "18.04.2008", "gender": "žena"})
    assert value == "080418/1234"
    assert "pohlaviu" in warning and "deliteľné" in warning


def test_rodne_cislo_format_error():
    with pytest.raises(ValidationError):
        ok("rodne_cislo", "12/34")


def test_zip_slovak_formatted_foreign_kept():
    assert ok("zip", "81108", {"perm_country": "Slovensko"}, "perm_zip")[0] == "811 08"
    assert ok("zip", "79000", {"perm_country": "Ukrajina"}, "perm_zip")[0] == "79000"
    with pytest.raises(ValidationError):
        ok("zip", "8110", {"perm_country": "Slovensko"}, "perm_zip")


def test_school_code_padded_to_nine_digits():
    assert ok("school_code", "790200")[0] == "000790200"


@pytest.mark.parametrize("raw,expected", [("7902J00", "7902J00"), ("7902 J", "7902J00"), ("25611", "2561100")])
def test_field_code(raw, expected):
    assert ok("field_code", raw)[0] == expected


def test_email_and_phone():
    assert ok("email", "Jana@Example.org")[0] == "jana@example.org"
    assert ok("phone", "+421900111101")[0] == "+421 900 111 101"
    with pytest.raises(ValidationError):
        ok("email", "not-an-email")


def test_averages_and_grades():
    assert ok("averages", "1.25 1,3")[0] == ["1,25", "1,30"]
    assert ok("grades_table", [["Matematika", "1", "2"]])[0] == [["Matematika", "1", "2"]]
    with pytest.raises(ValidationError):
        ok("grades_table", [["Matematika", "7"]])
