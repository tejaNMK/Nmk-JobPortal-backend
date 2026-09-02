from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class DetailSchema(BaseModel, Generic[T]):

    status: str
    message: str
    result: Optional[T] = None


class FieldError(BaseModel):
    field: str
    message: str


class ErrorDetailSchema(BaseModel):
    code: str
    details: str
    fields: Optional[List[FieldError]] = None


class ResponseSchema(BaseModel, Generic[T]):
    success: bool = True
    status: int = 200
    message: str
    data: Optional[T] = None
    error: Optional[ErrorDetailSchema] = None


class Request(BaseModel, Generic[T]):
    parameter: Optional[T] = None


class Response(BaseModel, Generic[T]):

    code: str
    status: str
    message: str
    result: Optional[T] = None


def success_response(
    data: Optional[T] = None,
    message: str = "Success",
    status: int = 200,
) -> ResponseSchema[T]:

    return ResponseSchema(
        success=True,
        status=status,
        message=message,
        data={} if data is None else data,
    )


def created_response(
    data: Optional[T] = None,
    message: str = "Resource created successfully",
) -> ResponseSchema[T]:
    return success_response(data=data, message=message, status=201)


def error_response(
    status: int,
    message: str,
    code: str = "ERROR",
    details: Optional[str] = None,
    fields: Optional[List[FieldError]] = None,
) -> ResponseSchema[None]:

    return ResponseSchema(
        success=False,
        status=status,
        message=message,
        error=ErrorDetailSchema(
            code=code,
            details=details or message,
            fields=fields,
        ),
    )
