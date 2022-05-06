from lib2to3.pgen2.token import OP
from typing import Union, Optional, List

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


@router.get("/", response_model=errata_schema.ErrataRecord)
async def get_errata_record(
    errata_id: str,
    db: database.Session = Depends(get_db),
):
    return await errata_crud.get_errata_record(
        db,
        errata_id,
    )


@router.get("/query/", response_model=errata_schema.ErrataListResponse)
async def list_errata_records(
    pageNumber: Optional[int] = None,
    id: Optional[str] = None,
    title: Optional[str] = None,
    platformId: Optional[int] = None,
    cveId: Optional[str] = None,
    db: database.Session = Depends(get_db),
):
    return await errata_crud.list_errata_records(
        db,
        page=pageNumber,
        errata_id=id,
        title=title,
        platform=platformId,
        cve_id=cveId,
    )


@router.get("/all/", response_model=List[errata_schema.CompactErrataRecord])
async def list_all_errata_records(
    db: database.Session = Depends(get_db),
):
    return [
        {"id": record.id, "updated_date": record.updated_date}
        for record in (await errata_crud.list_errata_records(db, compact=True))[
            "records"
        ]
    ]
