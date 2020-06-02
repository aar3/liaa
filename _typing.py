# pytlin: disable=unused-import
from asyncio import (
    Handle,
    Future,
)

from mypy_extensions import VarArg

from typing import (
    Union,
    Dict,
    List,
    Optional,
    Generic,
    OrderedDict as TOrderedDict,
    Callable,
    Coroutine,
    Iterator,
    Generic,
    Any,
    Tuple,
    overload,
    Awaitable,
    TypeVar,
    Set,
    Hashable,
    Type,
)


T = TypeVar("T")
Function = Callable[..., T]
F = TypeVar("F", bound=Function)

PingNodeInfo = Tuple[int, str, int]
IndexNodeInfo = Tuple[str, Optional[bytes], float]
IndexNodeAsDict = Dict[str, Optional[bytes]]
GenericNodeInfo = Union[PingNodeInfo, IndexNodeInfo]

ResponseIndexItem = Tuple[bool, Union[PingNodeInfo, IndexNodeAsDict]]
ResponseIndex = Dict[str, ResponseIndexItem]

TKademliaProtocol = Any

ValueSpiderFindReturn = Union[Optional[bytes], ResponseIndexItem]
NodeSpiderFindReturn = Union[GenericNodeInfo, ResponseIndexItem]
