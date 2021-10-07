import datetime
import inspect
from abc import ABC, abstractmethod
from dataclasses import asdict
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
)

T = TypeVar("T")
JSON = Union[Dict[str, Any], List[Any], int, str, float, bool, None]


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


class Compound(ABC):
    @abstractmethod
    def as_json(self) -> JSON:
        pass

    @classmethod
    @abstractmethod
    def from_json(cls, parsed: JSON) -> "Compound":
        pass


class Obj(Compound):
    _conversion: Dict[str, Conversion]

    def as_json(self) -> JSON:
        obj = {}
        for name, item in asdict(self).items():
            field: Conversion = self._conversion[name]
            if isinstance(item, MaybeMissing):
                if item.has():
                    obj[name] = field.to_json(item.value())
            else:
                obj[name] = field.to_json(item)
        return obj

    @classmethod
    def from_json(cls, parsed: JSON) -> "Obj":
        assert isinstance(parsed, dict)
        kwargs = {}
        for name, t in cls.__annotations__.items():
            field: Conversion = cls._conversion[name]
            if (
                hasattr(t, "__origin__")
                and inspect.isclass(t.__origin__)
                and issubclass(t.__origin__, MaybeMissing)
            ):
                kwargs[name] = (
                    Jst(field.from_json(parsed[name])) if name in parsed else Miss()
                )
            else:
                kwargs[name] = field.from_json(parsed[name])
        return cls(**kwargs)  # type: ignore


class Arr(Compound, Generic[T]):
    conversion: Conversion[T]

    _items: List[T]

    def __init__(self, items: List[T]):
        self._items = items

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, item):
        return self._items[item]

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self._items == other._items
        return False

    def as_json(self) -> JSON:
        return [self.conversion.to_json(i) for i in self._items]

    @classmethod
    def from_json(cls, parsed: JSON) -> "Compound":
        assert isinstance(parsed, list)
        return cls([cls.conversion.from_json(i) for i in parsed])

    def __repr__(self):
        return f"{self.__class__.__name__}{self._items!r}"


class ObjWithAliases(Compound):
    _alias_to_actual: Dict[str, str]
    _conversion: Dict[str, Conversion]

    def as_json(self) -> JSON:
        obj = {}
        for name, item in asdict(self).items():
            field: Conversion = self._conversion[name]
            if isinstance(item, MaybeMissing):
                if item.has():
                    obj[self._maybe_renamed(name)] = field.to_json(item.value())
            else:
                obj[self._maybe_renamed(name)] = field.to_json(item)
        return obj

    @classmethod
    def from_json(cls, parsed: JSON) -> "Obj":
        assert isinstance(parsed, dict)
        kwargs = {}
        for name, t in cls.__annotations__.items():
            field: Conversion = cls._conversion[name]
            maybe_unescaped_name = cls._maybe_renamed(name)
            if (
                hasattr(t, "__origin__")
                and inspect.isclass(t.__origin__)
                and issubclass(t.__origin__, MaybeMissing)
            ):
                kwargs[name] = (
                    Jst(field.from_json(parsed[maybe_unescaped_name]))
                    if maybe_unescaped_name in parsed
                    else Miss()
                )
            else:
                kwargs[name] = field.from_json(parsed[maybe_unescaped_name])
        return cls(**kwargs)  # type:  ignore

    @classmethod
    def _maybe_renamed(cls, name: str) -> str:
        if name in cls._alias_to_actual:
            return cls._alias_to_actual[name]
        return name


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


class CompoundConv(Conversion[Compound]):
    def __init__(self, obj: Type[Compound]):
        self._obj: Type[Compound] = obj

    def to_json(self, value: Compound) -> JSON:
        return self._obj.as_json(value)

    def from_json(self, obj: JSON) -> Compound:
        return self._obj.from_json(obj)


class ConversionOf(Conversion[T]):
    def __init__(self, to_json: Callable[[T], JSON], from_json: Callable[[JSON], T]):
        self._to_json: Callable[[T], JSON] = to_json
        self._from_json: Callable[[JSON], T] = from_json

    def to_json(self, value: T) -> JSON:
        return self._to_json(value)

    def from_json(self, obj: JSON) -> T:
        return self._from_json(obj)


class WithTypeCheck(Conversion[T]):
    def __init__(self, t: Type[T], c: Conversion[T]):
        self._t: Type[T] = t
        self._c: Conversion[T] = c

    def to_json(self, value: T) -> JSON:
        assert isinstance(value, self._t), f"Value {value!r} is not of type {self._t!r}"
        return self._c.to_json(value)

    def from_json(self, obj: JSON) -> T:
        return self._c.from_json(obj)


def identity(obj: T) -> T:
    return obj


datetime_iso_format_conv = WithTypeCheck(
    datetime.datetime,
    ConversionOf(
        to_json=lambda v: v.isoformat(),
        from_json=lambda s: datetime.datetime.fromisoformat(cast(str, s)),
    ),
)

identity_conv: Conversion[JSON] = ConversionOf(to_json=identity, from_json=identity)

string_conv = WithTypeCheck(
    str,
    identity_conv,
)

float_conv = WithTypeCheck(float, identity_conv)

int_conv = WithTypeCheck(
    int,
    identity_conv,
)

bool_conv = WithTypeCheck(
    bool,
    identity_conv,
)
