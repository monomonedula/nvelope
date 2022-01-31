import datetime
import inspect
from abc import ABC, abstractmethod
from dataclasses import fields
from typing import (
    TypeVar,
    Union,
    Dict,
    Any,
    List,
    Generic,
    Type,
    Optional,
    Callable,
    cast,
    Mapping,
)

from jsonschema import validate

T = TypeVar("T")
JSON = Union[Dict[str, Any], List[Any], int, str, float, bool, None]


def asdict(obj):
    return {f.name: getattr(obj, f.name) for f in fields(obj)}


def maybe_missing_field(f) -> bool:
    if isinstance(f.type, str):
        return f.type.startswith("MaybeMissing[")
    return (
        hasattr(f.type, "__origin__")
        and inspect.isclass(f.type.__origin__)
        and issubclass(f.type.__origin__, MaybeMissing)
    )


class MaybeMissing(Generic[T], ABC):
    @abstractmethod
    def value(self) -> T:
        pass  # pragma: no cover

    @abstractmethod
    def has(self) -> bool:
        pass  # pragma: no cover


class Jst(MaybeMissing[T]):
    def __init__(self, v: T):
        self._val: T = v

    def value(self) -> T:
        return self._val

    def has(self) -> bool:
        return True

    def __repr__(self):
        return f"{self.__class__.__name__}[{self._val!r}]"  # type: ignore

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self._val == other._val
        return False


class Miss(MaybeMissing[T]):
    def has(self) -> bool:
        return False

    def value(self) -> T:
        raise ValueError("Missing value")

    def __repr__(self):
        return f"{self.__class__.__name__}"

    def __eq__(self, other):
        return isinstance(other, self.__class__)


class Conversion(Generic[T], ABC):
    @abstractmethod
    def to_json(self, value: T) -> JSON:
        pass

    @abstractmethod
    def from_json(self, obj: JSON) -> T:
        pass

    @abstractmethod
    def schema(self) -> Dict[str, JSON]:
        pass


class Compound(ABC):
    @abstractmethod
    def as_json(self) -> JSON:
        pass

    @classmethod
    @abstractmethod
    def from_json(cls, parsed: JSON) -> "Compound":
        pass

    @classmethod
    @abstractmethod
    def schema(cls) -> Dict[str, JSON]:
        pass


class Obj(Compound):
    _conversion: Dict[str, Conversion]

    def as_json(self) -> JSON:
        obj = {}
        for name, item in asdict(self).items():
            try:
                field: Conversion = self._conversion[name]
                if isinstance(item, MaybeMissing):
                    if item.has():
                        obj[name] = field.to_json(item.value())
                else:
                    obj[name] = field.to_json(item)
            except NvelopeError as e:
                raise NvelopeError(f"{name}.{e.path}") from e
            except Exception as e:
                raise NvelopeError(name) from e
        return obj

    @classmethod
    def from_json(cls, parsed: JSON) -> "Obj":
        assert isinstance(parsed, dict), f"{parsed!r} Is not a dict"
        kwargs = {}
        for f in fields(cls):
            try:
                conv: Conversion = cls._conversion[f.name]
                if maybe_missing_field(f):
                    kwargs[f.name] = (
                        Jst(conv.from_json(parsed[f.name]))
                        if f.name in parsed
                        else Miss()
                    )
                else:
                    kwargs[f.name] = conv.from_json(parsed[f.name])
            except NvelopeError as e:
                raise NvelopeError(f"{f.name}.{e.path}") from e
            except Exception as e:
                raise NvelopeError(f.name) from e
        return cls(**kwargs)  # type: ignore

    @classmethod
    def schema(cls) -> Dict[str, JSON]:
        return {
            "type": "object",
            "properties": {
                name: item.schema() for name, item in cls._conversion.items()
            },
            "required": [f.name for f in fields(cls) if not maybe_missing_field(f)],
        }


class Arr(Compound, Generic[T]):
    conversion: Conversion[T]

    _items: List[T]

    def __init__(self, items: List[T]):
        self._items: List[T] = items

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, item):
        return self._items[item]

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self._items == other._items
        return False

    def as_json(self) -> JSON:
        j = []
        for i, item in enumerate(self._items):
            try:
                j.append(self.conversion.to_json(item))
            except NvelopeError as e:
                raise NvelopeError(f"<{i}>.{e.path}") from e
            except Exception as e:
                raise NvelopeError(f"<{i}>") from e
        return j

    @classmethod
    def from_json(cls, parsed: JSON) -> "Compound":
        assert isinstance(parsed, list), f"{parsed!r} is not a list"
        arr = []
        for i, item in enumerate(parsed):
            try:
                arr.append(cls.conversion.from_json(item))
            except NvelopeError as e:
                raise NvelopeError(f"<{i}>.{e.path}") from e
            except Exception as e:
                raise NvelopeError(f"<{i}>") from e
        return cls(arr)

    @classmethod
    def schema(cls) -> Dict[str, JSON]:
        return {"type": "array", "items": cls.conversion.schema()}

    def __repr__(self):
        return f"{self.__class__.__name__}{self._items!r}"


class ObjWithAliases(Compound):
    _alias_to_actual: Dict[str, str]
    _conversion: Dict[str, Conversion]

    def as_json(self) -> JSON:
        obj = {}
        for name, item in asdict(self).items():
            try:
                field: Conversion = self._conversion[name]
                if isinstance(item, MaybeMissing):
                    if item.has():
                        obj[self._true_name(name)] = field.to_json(item.value())
                else:
                    obj[self._true_name(name)] = field.to_json(item)
            except NvelopeError as e:
                raise NvelopeError(f"{name}.{e.path}") from e
            except Exception as e:
                raise NvelopeError(name) from e
        return obj

    @classmethod
    def from_json(cls, parsed: JSON) -> "Obj":
        assert isinstance(parsed, dict), f"{parsed!r} is not a dict"
        kwargs = {}
        for field in fields(cls):
            try:
                conv: Conversion = cls._conversion[field.name]
                true_name = cls._true_name(field.name)
                if maybe_missing_field(field):
                    kwargs[field.name] = (
                        Jst(conv.from_json(parsed[true_name]))
                        if true_name in parsed
                        else Miss()
                    )
                else:
                    kwargs[field.name] = conv.from_json(parsed[true_name])
            except NvelopeError as e:
                raise NvelopeError(f"{field.name}.{e.path}") from e
            except Exception as e:
                raise NvelopeError(field.name) from e
        return cls(**kwargs)  # type:  ignore

    @classmethod
    def _true_name(cls, name: str) -> str:
        return cls._alias_to_actual.get(name, name)

    @classmethod
    def schema(cls) -> Dict[str, JSON]:
        return {
            "type": "object",
            **{
                cls._true_name(name): item.schema()
                for name, item in cls._conversion.items()
            },
        }


class OptionalConv(Conversion[Optional[T]]):
    def __init__(self, f: Conversion[T]):
        self._f: Conversion[T] = f

    def to_json(self, value: Optional[T]) -> JSON:
        if value is None:
            return None
        return self._f.to_json(value)

    def from_json(self, obj: JSON) -> Optional[T]:
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
    def __init__(self, obj: Type[Compound]):
        self._obj: Type[Compound] = obj

    def to_json(self, value: Compound) -> JSON:
        return self._obj.as_json(value)

    def from_json(self, obj: JSON) -> Compound:
        return self._obj.from_json(obj)

    def schema(self) -> Dict[str, JSON]:
        return self._obj.schema()


class ConversionOf(Conversion[T]):
    def __init__(
        self,
        to_json: Callable[[T], JSON],
        from_json: Callable[[JSON], T],
        schema: Dict[str, JSON],
    ):
        self._to_json: Callable[[T], JSON] = to_json
        self._from_json: Callable[[JSON], T] = from_json
        self._schema: Dict[str, JSON] = schema

    def to_json(self, value: T) -> JSON:
        return self._to_json(value)

    def from_json(self, obj: JSON) -> T:
        return self._from_json(obj)

    def schema(self) -> Dict[str, JSON]:
        return self._schema


class WithTypeCheck(Conversion[T]):
    def __init__(self, t: Type[T], c: Conversion[T]):
        self._t: Type[T] = t
        self._c: Conversion[T] = c

    def to_json(self, value: T) -> JSON:
        assert isinstance(value, self._t), f"Value {value!r} is not of type {self._t!r}"
        return self._c.to_json(value)

    def from_json(self, obj: JSON) -> T:
        return self._c.from_json(obj)

    def schema(self) -> Dict[str, JSON]:
        return self._c.schema()


class WithTypeCheckOnRead(Conversion[T]):
    def __init__(self, t: Type, c: Conversion[T]):
        self._t: Type = t
        self._c: Conversion[T] = c

    def to_json(self, value: T) -> JSON:
        return self._c.to_json(value)

    def from_json(self, obj: JSON) -> T:
        assert isinstance(obj, self._t), f"Value {obj!r} is not of type {self._t!r}"
        return self._c.from_json(obj)

    def schema(self) -> Dict[str, JSON]:
        return self._c.schema()


_T = TypeVar("_T")


def with_type_check(
    on_dump: Type[_T], on_read: Type, c: Conversion[_T]
) -> Conversion[_T]:
    return WithTypeCheckOnRead(on_read, WithTypeCheck(on_dump, c))


def identity(obj: JSON) -> JSON:
    return obj


identity_conv: Conversion[JSON] = ConversionOf(
    to_json=identity, from_json=identity, schema={}
)


string_conv = with_type_check(
    str,
    str,
    ConversionOf(to_json=identity, from_json=identity, schema={"type": "string"}),
)

float_conv = with_type_check(
    float,
    float,
    ConversionOf(to_json=identity, from_json=identity, schema={"type": "number"}),
)

int_conv = with_type_check(
    int,
    int,
    ConversionOf(to_json=identity, from_json=identity, schema={"type": "integer"}),
)

bool_conv = with_type_check(
    bool,
    bool,
    ConversionOf(to_json=identity, from_json=identity, schema={"type": "boolean"}),
)


class ListConversion(Conversion[List[T]]):
    def __init__(self, item_conv: Conversion[T]):
        self._conv: Conversion[T] = item_conv

    def to_json(self, value: List[T]) -> JSON:
        assert isinstance(value, list), f"{value!r} is not a list"
        return [self._conv.to_json(v) for v in value]

    def from_json(self, obj: JSON) -> List[T]:
        assert isinstance(obj, list), f"{obj!r} is not a list"
        return [self._conv.from_json(v) for v in obj]

    def schema(self) -> Dict[str, JSON]:
        return {"type": "array", "items": self._conv.schema()}


K = TypeVar("K")
V = TypeVar("V")


class MappingConv(Conversion[Mapping[K, V]]):
    def __init__(self, key_conv: Conversion[K], val_conv: Conversion[V]):
        self._key_conv: Conversion[K] = key_conv
        self._val_conv: Conversion[V] = val_conv

    def to_json(self, value: Mapping[K, V]) -> JSON:
        d = {}
        for k, v in value.items():
            key = self._key_conv.to_json(k)
            assert isinstance(key, str), f"{value!r} is not a string"
            d[key] = self._val_conv.to_json(v)
        return d

    def from_json(self, obj: JSON) -> Mapping[K, V]:
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


class NvelopeError(Exception):
    def __init__(self, path, *args):
        self.path: str = path
        super(NvelopeError, self).__init__(*args)

    def __str__(self):
        base = f"Path: {self.path!r}"
        if self.args:
            return f"{base}; {','.join(self.args)}"
        return base


class WithSchema(Conversion[T]):
    def __init__(self, c: Conversion[T], schema: Dict[str, JSON]):
        self._c: Conversion[T] = c
        self._schema: Dict[str, JSON] = schema

    def to_json(self, value: T) -> JSON:
        return self._c.to_json(value)

    def from_json(self, obj: JSON) -> T:
        return self._c.from_json(obj)

    def schema(self) -> Dict[str, JSON]:
        return self._schema


class Validated(Conversion[T]):
    def __init__(self, c: Conversion[T]):
        self._c: Conversion[T] = c

    def to_json(self, value: T) -> JSON:
        j = self._c.to_json(value)
        validate(j, self.schema())
        return j

    def from_json(self, obj: JSON) -> T:
        validate(obj, self.schema())
        return self._c.from_json(obj)

    def schema(self) -> Dict[str, JSON]:
        return self._c.schema()


datetime_iso_format_conv: Conversion[datetime.datetime] = ConversionOf(
    to_json=lambda v: v.isoformat(),
    from_json=lambda s: datetime.datetime.fromisoformat(cast(str, s)),
    schema={
        "type": "string",
        "pattern": r"^(-?(?:[1-9][0-9]*)?[0-9]{4})-(1[0-2]|0[1-9])-(3[01]|0[1-9]|[12][0-9])T(2[0-3]|[01][0-9]):([0-5][0-9]):([0-5][0-9])(\.[0-9]+)?(Z|[+-](?:2[0-3]|[01][0-9]):[0-5][0-9])?$",
    },
)
