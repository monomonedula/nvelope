[![codecov](https://codecov.io/gh/monomonedula/nvelope/branch/master/graph/badge.svg?token=yunFiDdUEK)](https://codecov.io/gh/monomonedula/nvelope)
[![Build Status](https://app.travis-ci.com/monomonedula/nvelope.svg?branch=master)](https://app.travis-ci.com/monomonedula/nvelope)
# nvelope

Define your JSON schema as Python dataclasses

## Installation
`pip install nvelope`


## The problem it solves

This is basically sommething like JSON-schema, but it works 
with static type checking, since the classes you define are just regular
python dataclasses which can (and should) be type checked with `mypy` library.


It also lets not to just define the structure of your JSON data in a
single place in your
python code, but also to define
custom checks and conversions from/to JSON for any type you want.

### Original use case
Say you have two
microservices communicating via JSON messages, both written in python.

You may define a shared package with the messages definition 
and use the model's `.as_json()` method on one end to serialize the message
and `.form_json()` on the other to convert it into a DTO, 
checking and modifying the fields and their values along
the way exactly how you defined it in a single place.

Combining this with static type checking (and maybe some unit tests)
you can ensure that any message one microservice can send,
the other can read as long as they use the same model to pack/unpack their JSONs.

## Usage

Say you have a JSON representing a user in your app looking something like this
```json
{
    "id": 530716139,
    "username": "johndoe",
    "language_code": "en"
}
```

You define an envelope for it

```python
from dataclasses import dataclass
from typing import Optional

from nvelope import (Obj, int_conv, string_conv)

@dataclass      # note the @dataclass decorator, it is important
class User(Obj):
    _conversion = {
        "id": int_conv,
        "language_code": string_conv,
        "username": string_conv,
    }

    id: int
    language_code: Optional[str]
    username: Optional[str]

```


Now you have a model that knows how to read data from the JSON 
(not the raw string, actually, but to the types that are allowed by the
standard `json.dumps` function e.g. `dict`, `list`, `str`, `int`, `float`, `bool`, `None` ) ...

```python

user = User.from_json(
    {
        "id": 530716139,
        "username": "johndoe",
        "language_code": "en"
    }
)
```
... and knows how to convert itself into JSON 

```python
User(
    id=530716139,
    username="johndoe",
    language_code="en",
).as_json() 

# returns a dictionary {
#     "id": 530716139,
#     "username": "johndoe",
#     "language_code": "en"
# }
```


### Compound envelopes
You can also define compound envelopes.

Say we want to define a message and include info about the sender.
Having defined the `User` envelope, we can do it like this:

```python

from nvelope import CompoundConv

@dataclass
class Message(Obj):
    _conversion = {
        "message_id": int_conv,
        "from_": CompoundConv(User),
        "text": string_conv,
    }

    from_: User
    text: str
    message_id: int
```
and use it the same way:

```python
# reading an obj from json like this

Message.from_json(
    {
        "message_id": 44,
        "text": "hello there",
        "from_": {
            "id": 530716139,
            "username": "johndoe",
            "language_code": "en"
        }
    }
)

# and dumping an object to json like this
Message(
    message_id=44,
    text="whatever",
    from_=User(
        id=530716139,
        username="johndoe",
        language_code="en",
    )
).as_json()
```


### Arrays

This is how you define arrays:

```python
from nvelope import Arr


class Users(Arr):
    conversion = CompoundConv(User)


# Same API inherited from nvelope.Compound interface

Users.from_json(
    [
        {
            "id": 530716139,
            "username": "johndoe",
            "language_code": "en",
        },
        {
            "id": 452341341,
            "username": "ivandrago",
            "language_code": "ru",
        }
    ]
)

Users(
    [
        User(
            id=530716139,
            username="johndoe",
            language_code="en",
        ),
        User(
            id=452341341,
            username="ivandrago",
            language_code="ru",
        ),
    ]
).as_json()
```

### Field aliases

At some point you may need to define an envelope for an API containing certain field names which cannot be
used in python since they are reserved keywords.

There's a solution for this:

```python
from nvelope import ObjWithAliases

@dataclass
class Comment(ObjWithAliases):
    _conversion = {
        "text": string_conv,
        "from_": int_conv,
    }
    
    
    _alias_to_actual = {
        "from_": "from",
    }
    
    text: str
    from_: User

```

In this case `from` key gets replaced by `from_` in the python model. 

### Missing and optional fields

There's a difference between fields that can be set to `None` and fields which may be missing in the JSON at all.

This is how you specify that a some field may be missing from the JSON and that's OK:
```python
from typing import Optional

from nvelope import MaybeMissing
from nvelope import OptionalConv

@dataclass
class Comment(ObjWithAliases):
    _alias_to_actual = {
        "from_": "from",
    }
    
    text: str
    img: Optional[str]          # this field can be set to None (null), but is must always be present in the JSON
    from_: MaybeMissing[User]   # this field can be missing from JSON body

    _conversion = {
        "text": string_conv,
        "img": OptionalConv(string_conv),   # note the wrapping with OptionalConv
        "from_": int_conv,
    }

```

This is how you check if the `MaybeMissing` field is actually missing
```python
comment.from_.has()     # returns False if the field is missing
```

and this is how you get the value:
```python
comment.value()     # raises an error if there's no value, 
                    # so it is recommended to check the output of .has()
                    #  before calling .value() 
```


### Custom conversions


You may define a custom conversions inheriting from `nvelope.nvelope.Conversion` abstract base class 
or using `nvelope.nvelope.ConversionOf` class. 

For example, this is how `datetime_iso_format_conv` is defined:

```python
from nvelope import WithTypeCheck, ConversionOf

datetime_iso_format_conv = WithTypeCheck(
    datetime.datetime,
    ConversionOf(
        to_json=lambda v: v.isoformat(),
        from_json=lambda s: datetime.datetime.fromisoformat(s),
    ),
)

```

Say we want to jsonify a `datetime` field as POSIX timestamp, instead of storing it in ISO string format.

```python
datetime_timestamp_conv = ConversionOf(
    to_json=lambda v: v.timestamp(),
    from_json=lambda s: datetime.datetime.fromtimestamp(s),
)
```

We could also add `WithTypeCheck` wrapper in order to add explicit check that 
the value passed into `.from_json()`
is indeed `float`.

```python
datetime_timestamp_conv = WithTypeCheck(
    float,
    ConversionOf(
        to_json=lambda v: v.timestamp(),
        from_json=lambda s: datetime.datetime.fromtimestamp(s),
    )
)
```

