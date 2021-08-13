from fastapi import APIRouter, Depends

from alws.dependencies import get_db, JWTBearer
from alws import database, crud
from alws.schemas import artifact_schema


router = APIRouter(
    prefix='/artifacts',
    tags=['artifacts'],
    dependencies=[Depends(JWTBearer())]
)


@router.get('/{artifact_id}/', response_model=artifact_schema.Artifact)
async def get_artifact(
            artifact_id: int,
            db: database.Session = Depends(get_db)
        ):
    return await crud.get_artifact(db, artifact_id)
