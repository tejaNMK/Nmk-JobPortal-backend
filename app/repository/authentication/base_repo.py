from typing import Generic, TypeVar, Type

from fastapi import HTTPException
from sqlalchemy import delete as sql_delete
from sqlalchemy import update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import commit_rollback



T = TypeVar("T")


class BaseRepo:

    model: Type[T]

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs):

        model = cls.model(**kwargs)

        session.add(model)

        try:
            await commit_rollback(session)
        except IntegrityError as e:
            await session.rollback()

            message = str(e).lower()
            if "uq_users_mobile" in message or "mobile_number" in message:
                raise HTTPException(status_code=400, detail="Mobile number already exists!")
            if "uq_users_email" in message or "email" in message:
                raise HTTPException(status_code=400, detail="Email already exists!")

            raise

        return model

    @classmethod
    async def get_all(cls, session: AsyncSession):

        query = select(cls.model)

        result = await session.execute(query)

        return result.scalars().all()

    @classmethod
    async def get_by_id(cls, session: AsyncSession, model_id):

        pk = cls.get_primary_key()

        query = select(cls.model).where(pk == model_id)

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @classmethod
    async def update(cls, session: AsyncSession, model_id, **kwargs):

        pk = cls.get_primary_key()

        query = (
            sql_update(cls.model)
            .where(pk == model_id)
            .values(**kwargs)
            .execution_options(synchronize_session="fetch")
        )

        await session.execute(query)

        await commit_rollback(session)

    @classmethod
    async def delete(cls, session: AsyncSession, model_id):

        pk = cls.get_primary_key()

        query = sql_delete(cls.model).where(pk == model_id)

        await session.execute(query)

        await commit_rollback(session)


    @classmethod
    def get_primary_key(cls):

        return list(cls.model.__table__.primary_key.columns)[0]


