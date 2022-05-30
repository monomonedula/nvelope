from enum import Enum, IntEnum

from nvelope import EnumConversion
import pytest


def test_enum_conv():
    class Foo(Enum):
        x = 1
        y = 2
        z = 3

    assert EnumConversion(Foo).schema() == {"type": "integer", "enum": [1, 2, 3]}
    assert EnumConversion(Foo).to_json(Foo.x)
    assert EnumConversion(Foo).from_json(3)
    with pytest.raises(ValueError):
        assert EnumConversion(Foo).from_json(5)


def test_enum_conv_schema():
    class Foo(Enum):
        x = 1
        y = 2

    class Foo1(IntEnum):
        x = 1
        y = 2

    class Foo2(str, Enum):
        x = "foo"
        y = "bar"

    class Foo3(float, Enum):
        x = 1.2
        y = 4.6

    assert EnumConversion(Foo).schema() == {"type": "integer", "enum": [1, 2]}
    assert EnumConversion(Foo1).schema() == {"type": "integer", "enum": [1, 2]}
    assert EnumConversion(Foo2).schema() == {"type": "string", "enum": ["foo", "bar"]}
    assert EnumConversion(Foo3).schema() == {"type": "number", "enum": [1.2, 4.6]}


def test_enum_conv_schema_err():
    class Foo(dict, Enum):
        x = {"foo": 1}
        y = {"boo": 4}

    with pytest.raises(TypeError):
        assert EnumConversion(Foo)
