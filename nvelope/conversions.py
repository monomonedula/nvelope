import datetime
from typing import (
    cast,
    Optional,
    Dict,
    Callable,
    Type,
    List,
    TypeVar,
    Mapping,
)

from nvelope import Conversion, JSON
from nvelope.nvelope import Compound

_T = TypeVar("_T")


class ConversionOf(Conversion[_T]):
    """
    A conversion constructed from the given to_json, from_json function and schema value.

    :param to_json:     function to convert the type T to JSON
    :param from_json:   function to convert JSON to type T
    :param schema:      json-schema this conversion is intended for
    """

    def __init__(
        self,
        to_json: Callable[[_T], JSON],
        from_json: Callable[[JSON], _T],
        schema: Dict[str, JSON],
    ):
        self._to_json: Callable[[_T], JSON] = to_json
        self._from_json: Callable[[JSON], _T] = from_json
        self._schema: Dict[str, JSON] = schema

    def to_json(self, value: _T) -> JSON:
        return self._to_json(value)

    def from_json(self, obj: JSON) -> _T:
        return self._from_json(obj)

    def schema(self) -> Dict[str, JSON]:
        return self._schema


class WithTypeCheckOnDump(Conversion[_T]):
    """
    Decorates the wrapped conversion with an explicit type assertion for the `to_json` method input.

    :param t: expected input type for to_json method
    :param c: the conversion being wrapped
    """

    def __init__(self, t: Type[_T], c: Conversion[_T]):
        self._t: Type[_T] = t
        self._c: Conversion[_T] = c

    def to_json(self, value: _T) -> JSON:
        assert isinstance(value, self._t), f"Value {value!r} is not of type {self._t!r}"
        return self._c.to_json(value)

    def from_json(self, obj: JSON) -> _T:
        return self._c.from_json(obj)

    def schema(self) -> Dict[str, JSON]:
        return self._c.schema()


class WithTypeCheckOnRead(Conversion[_T]):
    """
    Decorates the wrapped conversion with an explicit type assertion for the `from_json` method input.

    :param t: expected input type for from_json method
    :param c: the conversion being wrapped
    """

    def __init__(self, t: Type, c: Conversion[_T]):
        self._t: Type = t
        self._c: Conversion[_T] = c

    def to_json(self, value: _T) -> JSON:
        return self._c.to_json(value)

    def from_json(self, obj: JSON) -> _T:
        assert isinstance(obj, self._t), f"Value {obj!r} is not of type {self._t!r}"
        return self._c.from_json(obj)

    def schema(self) -> Dict[str, JSON]:
        return self._c.schema()


def with_type_checks(
    on_dump: Type[_T], on_read: Type, c: Conversion[_T]
) -> Conversion[_T]:
    """
    Wraps given conversion with :class:`WithTypeCheckOnDump` and with :class:`WithTypeCheckOnRead`.

    :param on_dump: type parameter for WithTypeCheckOnDump wrapper
    :param on_read: type parameter for WithTypeCheckOnRead wrapper
    :param c:       the conversion being decorated
    :return:        the wrapped conversion
    """
    return WithTypeCheckOnRead(on_read, WithTypeCheckOnDump(on_dump, c))


def _identity(obj: JSON) -> JSON:
    return obj


identity_conv: Conversion[JSON] = ConversionOf(
    to_json=_identity, from_json=_identity, schema={}
)
string_conv = with_type_checks(
    str,
    str,
    ConversionOf(to_json=_identity, from_json=_identity, schema={"type": "string"}),
)
float_conv = with_type_checks(
    float,
    float,
    ConversionOf(to_json=_identity, from_json=_identity, schema={"type": "number"}),
)
int_conv = with_type_checks(
    int,
    int,
    ConversionOf(to_json=_identity, from_json=_identity, schema={"type": "integer"}),
)
bool_conv = with_type_checks(
    bool,
    bool,
    ConversionOf(to_json=_identity, from_json=_identity, schema={"type": "boolean"}),
)

datetime_iso_format_conv: Conversion[datetime.datetime] = ConversionOf(
    to_json=lambda v: v.isoformat(),
    from_json=lambda s: datetime.datetime.fromisoformat(cast(str, s)),
    schema={
        "type": "string",
        "pattern": r"^(-?(?:[1-9][0-9]*)?[0-9]{4})-(1[0-2]|0[1-9])-(3[01]|0[1-9]|[12][0-9])T(2[0-3]|[01][0-9]):([0-5][0-9]):([0-5][0-9])(\.[0-9]+)?(Z|[+-](?:2[0-3]|[01][0-9]):[0-5][0-9])?$",
    },
)
datetime_timestamp_conv: Conversion[datetime.datetime] = ConversionOf(
    to_json=lambda v: v.timestamp(),
    from_json=lambda s: datetime.datetime.fromtimestamp(cast(float, s)),
    schema={"type": "number"},
)


class OptionalConv(Conversion[Optional[_T]]):
    """
    A decorator creating Conversion[Optional[T]] from a Conversion[T] instance

    :param f:   conversion to be decorated
    """

    def __init__(self, f: Conversion[_T]):
        self._f: Conversion[_T] = f

    def to_json(self, value: Optional[_T]) -> JSON:
        if value is None:
            return None
        return self._f.to_json(value)

    def from_json(self, obj: JSON) -> Optional[_T]:
        if obj is None:
            return None
        return self._f.from_json(obj)

    def schema(self) -> Dict[str, JSON]:
        s = self._f.schema()
        if "type" in s:
            s = s.copy()
            if not isinstance(s["type"], list):
                s["type"] = [s["type"]]
            s["type"].append("null")
        return s


class CompoundConv(Conversion[Compound]):
    """
    Create a conversion for a :class:`nvelope.nvelope.Compound` type.

    :param obj: the Compound subtype
    """

    def __init__(self, obj: Type[Compound]):
        self._obj: Type[Compound] = obj

    def to_json(self, value: Compound) -> JSON:
        return self._obj.as_json(value)

    def from_json(self, obj: JSON) -> Compound:
        return self._obj.from_json(obj)

    def schema(self) -> Dict[str, JSON]:
        return self._obj.schema()


class ListConversion(Conversion[List[_T]]):
    """
    A decorator creating Conversion[List[T]] from a Conversion[T] instance

    :param item_conv:  the conversion being wrapped
    """

    def __init__(self, item_conv: Conversion[_T]):
        self._conv: Conversion[_T] = item_conv

    def to_json(self, value: List[_T]) -> JSON:
        assert isinstance(value, list), f"{value!r} is not a list"
        return [self._conv.to_json(v) for v in value]

    def from_json(self, obj: JSON) -> List[_T]:
        assert isinstance(obj, list), f"{obj!r} is not a list"
        return [self._conv.from_json(v) for v in obj]

    def schema(self) -> Dict[str, JSON]:
        return {"type": "array", "items": self._conv.schema()}


_K = TypeVar("_K")
_V = TypeVar("_V")


class MappingConv(Conversion[Mapping[_K, _V]]):
    """
    A conversion for a mapping without keys known in advance.

    :param key_conv:    a conversion for the key type
    :param val_conv:    a conversion for the value type
    """

    def __init__(self, key_conv: Conversion[_K], val_conv: Conversion[_V]):
        self._key_conv: Conversion[_K] = key_conv
        self._val_conv: Conversion[_V] = val_conv

    def to_json(self, value: Mapping[_K, _V]) -> JSON:
        d = {}
        for k, v in value.items():
            key = self._key_conv.to_json(k)
            assert isinstance(key, str), f"{value!r} is not a string"
            d[key] = self._val_conv.to_json(v)
        return d

    def from_json(self, obj: JSON) -> Mapping[_K, _V]:
        assert isinstance(obj, dict), f"{obj!r} is not a dict"
        return {
            self._key_conv.from_json(k): self._val_conv.from_json(v)
            for k, v in obj.items()
        }

    def schema(self) -> Dict[str, JSON]:
        return {
            "type": "object",
            "additionalProperties": self._val_conv.schema(),
        }


class WithSchema(Conversion[_T]):
    """
    Decorate a conversion to return a different json schema from the `schema` method

    :param c:   the conversion being wrapped
    :param schema:  the new json schema
    """

    def __init__(self, c: Conversion[_T], schema: Dict[str, JSON]):
        self._c: Conversion[_T] = c
        self._schema: Dict[str, JSON] = schema

    def to_json(self, value: _T) -> JSON:
        return self._c.to_json(value)

    def from_json(self, obj: JSON) -> _T:
        return self._c.from_json(obj)

    def schema(self) -> Dict[str, JSON]:
        return self._schema
