from asyncio import (
    Handle,
    Future,
)

from typing import (
    Union,
    Dict,
    List,
    Any,
    Optional,
    Generic,
    OrderedDict,
    Callable,
    Iterator,
    Tuple,
    Awaitable,
    TypeVar,
    Set,
    Hashable
)


T = TypeVar("T", bound=Any)
Function = Callable[..., Any]
F = TypeVar("F", bound=Function)

KeyValueResponse = Dict[str, Any]
PeerInfoResponse = Tuple[int, str, int]
Response = Tuple[bool, Union[List[PeerInfoResponse], KeyValueResponse]]
