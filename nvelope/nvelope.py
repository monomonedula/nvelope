import inspect
from abc import ABC, abstractmethod
from dataclasses import fields, is_dataclass, Field
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
    """
    Converts a dataclass instance to a dictionary.

    :param obj: a dataclass instance
    :return: a dict mapping the instance attribute name to their values
    """
    return {f.name: getattr(obj, f.name) for f in fields(obj)}


def maybe_missing_field(f: Field) -> bool:
    """
    Determine if a dataclass field is :class:`nvelope.nvelope.MaybeMissing`

    :param f:   dataclass field
    :return:    True if the field type is MaybeMissing
    """
    if isinstance(f.type, str):
        return f.type.startswith("MaybeMissing[")
    return (
        hasattr(f.type, "__origin__")
        and inspect.isclass(f.type.__origin__)
        and issubclass(f.type.__origin__, MaybeMissing)
    )


class MaybeMissing(Generic[_T], ABC):
    """
    A generic interface for fields that may or may not be present in JSON object.

    Use its subclass :class:`nvelope.nvelop.Jst`
    to wrap actual values and :class:`nvelope.nvelop.Miss` class instance as a sentinel object.
    """

    @abstractmethod
    def value(self) -> _T:
        """
        Returns value if it has one. Raises :class:`ValueError` otherwise.
        You should check .has() method output before calling .value().

        :return: encapsulated value if present.
        """
        pass  # pragma: no cover

    @abstractmethod
    def has(self) -> bool:
        """
        :return: True if the encapsulated value is present.
        """
        pass  # pragma: no cover


class Jst(MaybeMissing[_T]):
    """
    A :class:`MaybeMissing` implementation actually containing a value.
    """

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
    """
    A :class:`MaybeMissing` implementation to be used as a sentinel object for missing fields.
    """

    def has(self) -> bool:
        return False

    def value(self) -> _T:
        raise ValueError("Missing value")

    def __repr__(self):
        return f"{self.__class__.__name__}"

    def __eq__(self, other):
        return isinstance(other, self.__class__)


class Conversion(Generic[_T], ABC):
    """
    The generic interface for to/from json conversion definitions.
    """

    @abstractmethod
    def to_json(self, value: _T) -> JSON:
        """
        Convert passed value of type _T to JSON
        """
        pass  # pragma: no cover

    @abstractmethod
    def from_json(self, obj: JSON) -> _T:
        """
        Convert passed JSON to type _T
        """
        pass  # pragma: no cover

    @abstractmethod
    def schema(self) -> Dict[str, JSON]:
        """
        :return: json-schema the conversion is defined for.
        """
        pass  # pragma: no cover


class Compound(ABC):
    """
    An interface for models of compound JSON entities such as arrays and objects.
    """

    @abstractmethod
    def as_json(self) -> JSON:
        """
        :return: the object's data converted to JSON
        """
        pass  # pragma: no cover

    @classmethod
    @abstractmethod
    def from_json(cls, parsed: JSON) -> "Compound":
        """
        :param parsed: JSON object
        :return: a new Compound instance created from the passed JSON
        """
        pass  # pragma: no cover

    @classmethod
    @abstractmethod
    def schema(cls) -> Dict[str, JSON]:
        """
        :return: JSON schema this model is defined for.
        """
        pass  # pragma: no cover


class AliasTable:
    """
    Mapping for field name aliases
    """

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
        """
        :param name:    original field name
        :return:        name alias
        """
        return self._actual_to_alias.get(name, name)

    def actual(self, alias: str) -> str:
        """
        :param alias:   field name alias
        :return:        original name
        """
        return self._alias_to_actual.get(alias, alias)


class Obj(Compound):
    """
    A base class for JSON objects models.

    The basic use to define a model is the following:
        1) Subclass this class;
        2) wrap it with the standard dataclasses.dataclass decorator;
        3) define fields as you normally would for a dataclass;
        4) set _conversion class property as a dict mapping field names to their corresponding conversions;

    The conversions must implement :class:`nvelope.nvelope.Conversion`.


    You may also set _alias_table class property to a custom :class:`nvelope.nvelope.AliasTable`.
    This may be useful if the JSON contains python keywords like 'from', 'def,' etc.


    If you set _keep_undefined = True then when using .from_json() method to create the model instance from JSON,
    all fields from the JSON that are not part of expected schema are stored into the object's __dict__ attribute.


    Please refer to README.md for comprehensive examples.
    """

    _conversion: Dict[str, Conversion]
    _alias_table: AliasTable = AliasTable({})
    _keep_undefined = False

    def as_json(self) -> JSON:
        """
        :return: JSON representation of the current object
        """
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
        """
        :param parsed: a JSON dict
        :return: a new model instance
        """
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
        """
        :return: JSON schema the model is written for.
        """
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
    """
    A base class for JSON arrays models.

    The basic use to define a model is the following:
        1) Subclass this class;
        2) set the 'conversion' class to a conversion for the type this model is intended to contain.

    The conversions must implement :class:`nvelope.nvelope.Conversion`.

    Please refer to README.md for comprehensive examples.
    """

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
        """
        :return: JSON representation of the current object
        """
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
        """
        Creates model instance from the given array.

        :param parsed: a JSON dict
        :return: a new model instance
        """
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
        """
        :return: JSON schema the model is written for.
        """
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
    """ 
A class decorator validating correctness of :class:`nvelope.nvelope.Obj` and :class:`nvelope.nvelope.Arr` 
subclasses definition.
    """ ""
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
