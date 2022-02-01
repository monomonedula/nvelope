import datetime
from dataclasses import dataclass
from typing import Optional

import jsonschema.exceptions
import pytest
from jsonschema import validate

from nvelope import (
    int_conv,
    Obj,
    CompoundConv,
    string_conv,
    Arr,
    OptionalConv,
    bool_conv,
    MaybeMissing,
    ObjWithAliases,
    AliasTable,
)


def test_basic_schema():
    @dataclass
    class Bar(Obj):
        _conversion = {"xyz": int_conv}

        xyz: int

    class ArrInner(Arr):
        conversion = CompoundConv(Bar)

    @dataclass
    class Inner(Obj):
        _conversion = {
            "inner_field": string_conv,
            "arr_field": CompoundConv(ArrInner),
        }

        inner_field: str
        arr_field: ArrInner

    @dataclass
    class Dummy(Obj):
        _conversion = {
            "foo": CompoundConv(Inner),
        }
        foo: Inner

    assert Dummy.schema() == {
        "type": "object",
        "properties": {
            "foo": {
                "type": "object",
                "properties": {
                    "inner_field": {"type": "string"},
                    "arr_field": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"xyz": {"type": "integer"}},
                            "required": ["xyz"],
                        },
                    },
                },
                "required": [
                    "inner_field",
                    "arr_field",
                ],
            }
        },
        "required": ["foo"],
    }

    validate(
        Dummy(Inner("hello there", ArrInner([Bar(543)]))).as_json(), Dummy.schema()
    )


def test_schema_optional():
    @dataclass()
    class Foo(Obj):
        _conversion = {
            "abc": OptionalConv(string_conv),
        }

        abc: Optional[datetime.datetime]

    assert Foo.schema() == {
        "type": "object",
        "properties": {"abc": {"type": ["string", "null"]}},
        "required": ["abc"],
    }

    validate({"abc": None}, Foo.schema())
    validate({"abc": "hello"}, Foo.schema())
    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate({}, Foo.schema())


def test_schema_optional_obj():
    @dataclass
    class Inner(Obj):
        _conversion = {
            "abc": int_conv,
            "efg": bool_conv,
            "xyz": string_conv,
        }
        abc: int
        efg: bool
        xyz: str

    @dataclass
    class Foo(Obj):
        _conversion = {
            "opt": OptionalConv(CompoundConv(Inner)),
        }

        opt: Optional[Inner]

    assert Foo.schema() == {
        "type": "object",
        "properties": {
            "opt": {
                "type": ["object", "null"],
                "properties": {
                    "abc": {"type": "integer"},
                    "efg": {"type": "boolean"},
                    "xyz": {"type": "string"},
                },
                "required": ["abc", "efg", "xyz"],
            }
        },
        "required": ["opt"],
    }

    validate({"opt": None}, Foo.schema())
    validate({"opt": {"abc": 1234, "efg": False, "xyz": "Hello"}}, Foo.schema())
    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate({"opt": {"abc": 1234, "xyz": "Hello"}}, Foo.schema())


def test_validation_maybe_missing():
    @dataclass()
    class Foo(Obj):
        _conversion = {"xyz": string_conv, "abc": string_conv}
        xyz: MaybeMissing[str]
        abc: str

    assert Foo.schema() == {
        "type": "object",
        "properties": {"xyz": {"type": "string"}, "abc": {"type": "string"}},
        "required": ["abc"],
    }


def test_arr_schema():
    class Foo(Arr):
        conversion = string_conv

    assert Foo.schema() == {
        "type": "array",
        "items": {"type": "string"},
    }


def test_obj_with_aliases_schema():
    @dataclass
    class Foo(ObjWithAliases):
        _alias_table = AliasTable(
            alias_to_actual={
                "def_": "def",
            }
        )
        _conversion = {
            "def_": string_conv,
            "foo": int_conv,
        }

        def_: str
        foo: int

    assert Foo.schema() == {
        "type": "object",
        "properties": {
            "def": {"type": "string"},
            "foo": {"type": "integer"},
        },
        "required": ["def", "foo"],
    }
