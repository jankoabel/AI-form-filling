from formfill.fields import Anchor, Field, condition_holds, schema_from_json, schema_to_json
from formfill.forms import prihlaska


def test_conditions():
    values = {"citizenship": "SLOVENSKÉ", "n": 2}
    assert condition_holds(None, values)
    assert condition_holds({"field": "citizenship", "equals": "slovenské"}, values)
    assert condition_holds({"field": "citizenship", "not_in": ["ukrajinské"]}, values)
    assert not condition_holds({"field": "missing", "not_equals": "x"}, values)
    assert condition_holds({"field": "missing", "filled": False}, values)
    assert condition_holds({"all": [{"field": "n", "equals": 2}, {"any": [{"field": "n", "in": [1, 2]}]}]}, values)


def test_schema_roundtrip_is_lossless():
    fields = [Field("a", "A", "Q?", anchor=Anchor("Label", "Section", 1), options=["x"], when={"field": "b", "equals": "x"})]
    assert schema_from_json(schema_to_json(fields)) == fields
    known = schema_from_json(schema_to_json(prihlaska.FIELDS))
    assert [f.key for f in known] == [f.key for f in prihlaska.FIELDS]


def test_prihlaska_keys_unique():
    keys = [f.key for f in prihlaska.FIELDS]
    assert len(keys) == len(set(keys))


def test_derive_foreigner_maturant_and_level():
    d = prihlaska.derive({"citizenship": "ukrajinské", "maturita_year": "2027",
                          "academic_year": "2027/2028", "field_code": "2561M00"})
    assert d == {"_foreigner": True, "_current_maturant": True, "education_level": "M"}
    assert prihlaska.derive({"citizenship": "slovenské", "maturita_year": "2016",
                             "academic_year": "2027/2028"}) == {"_foreigner": False, "_current_maturant": False}
