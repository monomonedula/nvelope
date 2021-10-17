import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict

from nvelope.nvelope import (
    Obj,
    CompoundConv,
    int_conv,
    string_conv,
    MaybeMissing,
    Jst,
    Arr,
    ObjWithAliases,
    datetime_iso_format_conv,
    Miss,
    OptionalConv,
    ListConversion,
    MappingConv,
    ConversionOf,
)


@dataclass
class User(Obj):
    _conversion = {
        "id": int_conv,
        "language_code": string_conv,
        "username": string_conv,
    }

    id: int
    language_code: Optional[str]
    username: Optional[str]


@dataclass
class Message(Obj):
    _conversion = {
        "message_id": int_conv,
        "from_": CompoundConv(User),
        "text": string_conv,
    }
    from_: MaybeMissing[User]
    text: MaybeMissing[str]
    message_id: int


@dataclass
class Update(Obj):
    _conversion = {
        "update_id": int_conv,
        "message": CompoundConv(Message),
    }

    update_id: int
    message: MaybeMissing[Message]


class ArrayOfUpdate(Arr):
    conversion = CompoundConv(Update)


def test_obj_from_json():
    raw = {
        "update_id": 91120013,
        "message": {
            "message_id": 5,
            "from_": {
                "id": 530716123,
                "is_bot": False,
                "first_name": "monedu1a",
                "username": "be_patient_i_have_autism",
                "language_code": "en",
            },
            "chat": {
                "id": 530716123,
                "first_name": "monedu1a",
                "username": "be_patient_i_have_autism",
                "type": "private",
            },
            "date": 1632911451,
            "text": "foo",
        },
    }
    assert Update.from_json(raw) == Update(
        update_id=91120013,
        message=Jst(
            Message(
                from_=Jst(
                    User(
                        id=530716123,
                        language_code="en",
                        username="be_patient_i_have_autism",
                    ),
                ),
                text=Jst("foo"),
                message_id=5,
            )
        ),
    )


def test_array_of_objects_from_json():
    raw = [
        {
            "update_id": 91120013,
            "message": {
                "message_id": 5,
                "from_": {
                    "id": 530716123,
                    "is_bot": False,
                    "first_name": "monedu1a",
                    "username": "be_patient_i_have_autism",
                    "language_code": "en",
                },
                "date": 1632911451,
                "text": "foo",
            },
        },
        {
            "update_id": 91120015,
            "message": {
                "message_id": 6,
                "from_": {
                    "id": 530716166,
                    "is_bot": False,
                    "first_name": "Joe",
                    "username": "joerogan",
                    "language_code": "en",
                },
                "date": 1632911452,
                "text": "foo",
            },
        },
    ]
    assert ArrayOfUpdate.from_json(raw) == ArrayOfUpdate(
        [
            Update(
                update_id=91120013,
                message=Jst(
                    Message(
                        from_=Jst(
                            User(
                                id=530716123,
                                language_code="en",
                                username="be_patient_i_have_autism",
                            )
                        ),
                        text=Jst("foo"),
                        message_id=5,
                    ),
                ),
            ),
            Update(
                update_id=91120015,
                message=Jst(
                    Message(
                        from_=Jst(
                            User(id=530716166, language_code="en", username="joerogan")
                        ),
                        text=Jst("foo"),
                        message_id=6,
                    )
                ),
            ),
        ]
    )


def test_obj_to_json():
    raw = {
        "update_id": 91120013,
        "message": {
            "message_id": 5,
            "from_": {
                "id": 530716123,
                "username": "be_patient_i_have_autism",
                "language_code": "en",
            },
            "text": "foo",
        },
    }
    assert (
        Update(
            update_id=91120013,
            message=Jst(
                Message(
                    from_=Jst(
                        User(
                            id=530716123,
                            language_code="en",
                            username="be_patient_i_have_autism",
                        )
                    ),
                    text=Jst("foo"),
                    message_id=5,
                ),
            ),
        ).as_json()
        == raw
    )


def test_array_to_json():
    raw = [
        {
            "update_id": 91120013,
            "message": {
                "message_id": 5,
                "from_": {
                    "id": 530716123,
                    "username": "be_patient_i_have_autism",
                    "language_code": "en",
                },
                "text": "foo",
            },
        },
        {
            "update_id": 91120020,
            "message": {
                "message_id": 9,
                "from_": {
                    "id": 530716135,
                    "username": "be_patient_i_have_autism",
                    "language_code": "en",
                },
                "text": "foo bar",
            },
        },
    ]
    assert ArrayOfUpdate.from_json(raw).as_json() == raw


def test_maybe_missing_field():
    assert (
        Message(
            from_=Miss(),
            text=Jst("foooo"),
            message_id=4322,
        ).as_json()
        == {"message_id": 4322, "text": "foooo"}
    )
    assert Message.from_json({"message_id": 4322, "text": "foooo"}) == Message(
        from_=Miss(),
        text=Jst("foooo"),
        message_id=4322,
    )


def test_optional_conv():
    assert OptionalConv(CompoundConv(User)).from_json(None) is None
    assert OptionalConv(CompoundConv(User)).to_json(None) is None
    assert (
        OptionalConv(CompoundConv(User)).from_json(
            {
                "language_code": "en",
                "id": 435424,
                "username": "joerogan",
            }
        )
        == User(language_code="en", id=435424, username="joerogan")
    )
    assert OptionalConv(CompoundConv(User)).to_json(
        User(language_code="en", id=435424, username="joerogan")
    ) == {
        "language_code": "en",
        "id": 435424,
        "username": "joerogan",
    }


def test_obj_with_aliases():
    @dataclass
    class Bar(Obj):
        _conversion = {"txt": string_conv}
        txt: str

    @dataclass
    class Foo(ObjWithAliases):
        _conversion = {
            "foo": string_conv,
            "from_": int_conv,
            "bar": CompoundConv(Bar),
            "baz": CompoundConv(Bar),
        }

        _alias_to_actual = {
            "from_": "from",
        }

        foo: str
        from_: int
        bar: MaybeMissing[Bar]
        baz: MaybeMissing[Bar]

    raw = {"foo": "some string", "from": 12345, "baz": {"txt": "hello there"}}
    assert Foo.from_json(raw) == Foo(
        foo="some string", from_=12345, bar=Miss(), baz=Jst(Bar("hello there"))
    )
    assert Foo.from_json(raw).as_json() == raw


def test_datetime_iso_conv():
    now = datetime.datetime.now()
    assert datetime_iso_format_conv.from_json(now.isoformat()) == now
    assert datetime_iso_format_conv.to_json(now) == now.isoformat()


def test_asdict_fix():
    @dataclass
    class Inner(Obj):
        _conversion = {
            "list_field": ListConversion(string_conv),
        }

        list_field: List[str]

    @dataclass
    class Dummy(Obj):
        _conversion = {
            "bl": CompoundConv(Inner),
        }
        bl: Inner

    assert Dummy(Inner(["111.33.33.33"])).as_json() == {
        "bl": {"list_field": ["111.33.33.33"]}
    }


def test_mapping_conv():
    @dataclass
    class Data(Obj):
        _conversion = {
            "mapping_field": MappingConv(
                key_conv=ConversionOf(
                    str,
                    int,
                ),
                val_conv=string_conv,
            )
        }
        mapping_field: Dict[int, str]

    assert Data({443: "hello there"}).as_json() == {
        "mapping_field": {"443": "hello there"}
    }
