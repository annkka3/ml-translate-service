from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.wallet import Wallet
from app.infrastructure.db.models.transaction import Transaction
from app.infrastructure.db.models.translation import Translation


class AdminActions:

    @staticmethod
    async def approve_bonus(
            db: AsyncSession, user_id: str, amount: int, description: str = "Бонус"
    ):
        result = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
        wallet = result.scalar_one_or_none()
        if not wallet:
            raise ValueError(f"Wallet not found for user {user_id}")

        wallet.balance += amount

        db.add(Transaction(
            user_id=user_id,
            amount=amount,
            type=description
        ))

        await db.commit()

    @staticmethod
    async def view_transactions(db: AsyncSession, user_id: str = None):
        query = select(Transaction)
        if user_id:
            query = query.where(Transaction.user_id == user_id)
        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def view_translations(db: AsyncSession, user_id: str = None):
        query = select(Translation)
        if user_id:
            query = query.where(Translation.user_id == user_id)
        result = await db.execute(query)
        return result.scalars().all()