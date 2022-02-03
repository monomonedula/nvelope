[![codecov](https://codecov.io/gh/monomonedula/nvelope/branch/master/graph/badge.svg?token=yunFiDdUEK)](https://codecov.io/gh/monomonedula/nvelope)
[![Build Status](https://app.travis-ci.com/monomonedula/nvelope.svg?branch=master)](https://app.travis-ci.com/monomonedula/nvelope)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Downloads](https://pepy.tech/badge/nvelope)](https://pepy.tech/project/nvelope)
# nvelope

Define your JSON schema as Python dataclasses

It's kinda like Pydantic but better.

Now with JSON-schema generation!

## Installation
`pip install nvelope`


## The problem it solves

With `nvelope` you can define dataclasses which know how to convert themselves from/to JSON.
All with custom checks and custom defined conversions from/to JSON for any type you want to put into your dataclass.

This lbirary was deisgned with extensibility in mind, 
so it relies on interfaces (for the most part) rather than 
some weird inheritance stuff and other magic.

You can (and probably should) take a look at the code! 
The code base is microscopic compared to Pydantic.



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

from nvelope import (Obj, int_conv, string_conv)

@dataclass      # note the @dataclass decorator, it is important
class User(Obj):
    _conversion = {
        "id": int_conv,
        "language_code": string_conv,
        "username": string_conv,
    }

    id: int
    language_code: str
    username: str

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
# reading an obj from parsed json like this

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

import json

json.dumps(
    Message(
        message_id=44,
        text="whatever",
        from_=User(
            id=530716139,
            username="johndoe",
            language_code="en",
        )
    ).as_json()
)
```


### Arrays

This is how you define arrays:

```python
from nvelope import Arr, CompoundConv


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
used in python since they are reserved keywords (such as `def`, `from`, etc.).

There's a solution for this:

```python
from dataclasses import dataclass
from nvelope import Obj, string_conv, CompoundConv, AliasTable

@dataclass
class Comment(Obj):
    _conversion = {
        "text": string_conv,
        "from_": CompoundConv(User),
    }
    
    
    _alias_table = AliasTable({"from_": "from"})
            
    text: str
    from_: User

```

In this case `from` key gets replaced by `from_` in the python model. 
The `from_` field gets translated back to `from` when calling `.as_json()`

### Missing and optional fields

There's a difference between fields that can be set to `None` and fields which may be missing in the JSON at all.

This is how you specify that a some field may be missing from the JSON and that's OK:
```python
from dataclasses import dataclass
from typing import Optional

from nvelope import MaybeMissing, Obj, OptionalConv, AliasTable

@dataclass
class Comment(Obj):
    _alias_table = AliasTable(
        {"from_": "from"}
    )
    
    text: str
    img: Optional[str]          # this field can be set to None (null), but is must always be present in the JSON
    from_: MaybeMissing[User]   # this field can be missing from JSON body

    _conversion = {
        "text": string_conv,
        "img": OptionalConv(string_conv),   # note the wrapping with OptionalConv
        "from_": CompoundConv(User),
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

### Json-schema support
The `Comment` model from we have defined generates schema like this:
```python
    Comment.schema()
```

with the returned schema looking like this:
```python
{
    "type": "object",
    "properties": {
        "from": {
            "properties": {
                "id": {"type": "integer"},
                "language_code": {"type": "string"},
                "username": {"type": "string"},
            },
            "required": ["id", "language_code", "username"],
            "type": "object",
        },
        "img": {"type": ["string", "null"]},
        "text": {"type": "string"},
    },
    "required": ["text", "img"],
}
```
**NOTE**: `nvelope` does not perform json schema checks.

### Custom conversions


You may define a custom conversions inheriting from `nvelope.nvelope.Conversion` abstract base class 
or using `nvelope.nvelope.ConversionOf` class. 

For example, this is how `datetime_iso_format_conv` is defined:

```python
from nvelope import WithTypeCheckOnDump, ConversionOf

datetime_iso_format_conv = WithTypeCheckOnDump(
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
    schema={"type": "number"},
)
```

We could also add `WithTypeCheckOnDump` wrapper in order to add explicit check that 
the value passed into `.from_json()`
is indeed `float`.

```python
from nvelope import ConversionOf

datetime_timestamp_conv = WithTypeCheckOnDump(
    float,
    ConversionOf(
        to_json=lambda v: v.timestamp(),
        from_json=lambda s: datetime.datetime.fromtimestamp(s),
        schema={"type": "number"},
    )
)
```

You may also go further and implement custom conversion.
Inherit from `nvelope.Conversion` interface, implement its abstract methods, and you are good to go.


### Custom compounds

You can also define custom alternatives to `nvelope.Obj` and `nvelope.Arr`.
It will work fine as long as they inherit `nvelope.Compound` interface.

It currently required 3 methods:
- `from_json` 
- `as_json`
- `schema`
