from typing import Union, Optional

from fastapi import (
    APIRouter,
    Depends,
)

from alws import database
from alws.dependencies import get_db, JWTBearer
from alws.schemas import errata_schema
from alws.crud import errata as errata_crud

router = APIRouter(
    prefix="/errata", tags=["errata"], dependencies=[Depends(JWTBearer())]
)


@router.post("/", response_model=errata_schema.CreateErrataResponse)
async def create_errata_record(
    errata: errata_schema.BaseErrataRecord, db: database.Session = Depends(get_db)
):
    record = await errata_crud.create_errata_record(
        db,
        errata,
    )
    return {"ok": bool(record)}


@router.get(
    "/",
    response_model=Union[errata_schema.ErrataListResponse, errata_schema.ErrataRecord],
)
async def list_errata_records(
    errataId: Optional[str] = None,
    pageNumber: Optional[int] = None,
    db: database.Session = Depends(get_db),
):
    return await errata_crud.list_errata_records(
        db, page=pageNumber, errata_record_id=errataId
    )
