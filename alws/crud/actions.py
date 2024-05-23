from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from alws.models import UserAction
from alws.perms.actions import ActionsList


async def ensure_all_actions_exist(session: AsyncSession):
    existing_actions = (
        (await session.execute(select(UserAction))).scalars().all()
    )

    existing_action_names = {a.name for a in existing_actions}
    new_actions = []

    for required_action in ActionsList:
        if required_action.name not in existing_action_names:
            new_actions.append(UserAction(**required_action.model_dump()))

    if new_actions:
        session.add_all(new_actions)
        await session.flush()
