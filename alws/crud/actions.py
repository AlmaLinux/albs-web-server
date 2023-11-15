from sqlalchemy.future import select

from alws.database import Session
from alws.models import UserAction
from alws.perms.actions import ActionsList


async def ensure_all_actions_exist(session: Session, commit: bool = False):
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
        if commit:
            await session.commit()
        else:
            await session.flush()
