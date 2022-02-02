import inspect
from abc import ABC, abstractmethod
from dataclasses import fields, is_dataclass
from functools import lru_cache
from typing import (
    TypeVar,
    Union,
    Dict,
    Any,
    List,
    Generic,
)

_T = TypeVar("_T")
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


class MaybeMissing(Generic[_T], ABC):
    @abstractmethod
    def value(self) -> _T:
        pass  # pragma: no cover

    @abstractmethod
    def has(self) -> bool:
        pass  # pragma: no cover


class Jst(MaybeMissing[_T]):
    def __init__(self, v: _T):
        self._val: _T = v

    def value(self) -> _T:
        return self._val

    def has(self) -> bool:
        return True

    def __repr__(self):
        return f"{self.__class__.__name__}[{self._val!r}]"  # type: ignore

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self._val == other._val
        return False


class Miss(MaybeMissing[_T]):
    def has(self) -> bool:
        return False

    def value(self) -> _T:
        raise ValueError("Missing value")

    def __repr__(self):
        return f"{self.__class__.__name__}"

    def __eq__(self, other):
        return isinstance(other, self.__class__)


class Conversion(Generic[_T], ABC):
    @abstractmethod
    def to_json(self, value: _T) -> JSON:
        pass  # pragma: no cover

    @abstractmethod
    def from_json(self, obj: JSON) -> _T:
        pass  # pragma: no cover

    @abstractmethod
    def schema(self) -> Dict[str, JSON]:
        pass  # pragma: no cover


class Compound(ABC):
    @abstractmethod
    def as_json(self) -> JSON:
        pass  # pragma: no cover

    @classmethod
    @abstractmethod
    def from_json(cls, parsed: JSON) -> "Compound":
        pass  # pragma: no cover

    @classmethod
    @abstractmethod
    def schema(cls) -> Dict[str, JSON]:
        pass  # pragma: no cover


class AliasTable:
    __slots__ = (
        "_alias_to_actual",
        "_actual_to_alias",
    )

    def __init__(self, alias_to_actual: Dict[str, str]):
        self._alias_to_actual: Dict[str, str] = alias_to_actual
        self._actual_to_alias: Dict[str, str] = {
            v: k for k, v in alias_to_actual.items()
        }

    def aliased(self, name: str) -> str:
        return self._actual_to_alias.get(name, name)

    def actual(self, alias: str) -> str:
        return self._alias_to_actual.get(alias, alias)


class Obj(Compound):
    _conversion: Dict[str, Conversion]
    _alias_table: AliasTable = AliasTable({})
    _keep_undefined = False

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
        if self._keep_undefined:
            for key, value in self.__dict__.items():
                if key not in obj:
                    obj[key] = value
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
        obj = cls(**kwargs)  # type:  ignore
        if cls._keep_undefined:
            for key, value in parsed.items():
                if cls._aliased(key) not in obj.__dict__:
                    obj.__dict__[key] = value
        return obj  # type:  ignore

    @classmethod
    def _true_name(cls, name: str) -> str:
        return cls._alias_table.actual(name)

    @classmethod
    def _aliased(cls, name: str) -> str:
        return cls._alias_table.aliased(name)

    @classmethod
    @lru_cache()
    def schema(cls) -> Dict[str, JSON]:
        return {
            "type": "object",
            "properties": {
                cls._true_name(name): item.schema()
                for name, item in cls._conversion.items()
            },
            "required": [
                cls._true_name(f.name)
                for f in fields(cls)
                if not maybe_missing_field(f)
            ],
        }


class Arr(Compound, Generic[_T]):
    conversion: Conversion[_T]

    _items: List[_T]

    def __init__(self, items: List[_T]):
        self._items: List[_T] = items

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
    @lru_cache()
    def schema(cls) -> Dict[str, JSON]:
        return {"type": "array", "items": cls.conversion.schema()}

    def __repr__(self):
        return f"{self.__class__.__name__}{self._items!r}"


class NvelopeError(Exception):
    def __init__(self, path, *args):
        self.path: str = path
        super(NvelopeError, self).__init__(*args)

    def __str__(self):
        base = f"Path: {self.path!r}"
        if self.args:
            return f"{base}; {','.join(self.args)}"
        return base


def validated(cls):
    if issubclass(cls, Obj):
        assert hasattr(
            cls, "_conversion"
        ), f"'_conversion' attribute is not defined for {cls!r}"
        assert is_dataclass(
            cls
        ), f"{cls!r} must be wrapped with a dataclasses.dataclass decorator"

        flds = set(f.name for f in fields(cls))
        conv_flds = set(cls._conversion.keys())
        if flds != conv_flds:
            flds_conv_diff = flds.difference(conv_flds)
            conv_flds_diff = conv_flds.difference(flds)
            msg = "Fields and conversions do not match! "
            if flds_conv_diff:
                msg += f"The following fields are missing in the {cls!r}._conversion map: {sorted(flds_conv_diff)}. "
            if conv_flds_diff:
                msg += f"The following keys from {cls!r}._conversion are not defined as attributes: {sorted(conv_flds_diff)}"
            raise AssertionError(msg)
    elif issubclass(cls, Arr):
        assert hasattr(
            cls, "conversion"
        ), f"'conversion' attribute is not defined for {cls!r}"
    return cls
