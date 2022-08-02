from typing import Optional, List

from fastapi import (
    APIRouter,
    Depends,
)

from alws import database
from alws.auth import get_current_user
from alws.dependencies import get_db
from alws.schemas import errata_schema
from alws.crud import errata as errata_crud

router = APIRouter(
    prefix="/errata", tags=["errata"], dependencies=[Depends(get_current_user)]
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


@router.get("/get_oval_xml/", response_model=str)
async def get_oval_xml(
    platform_name: str,
    db: database.Session = Depends(get_db),
):
    return await errata_crud.get_oval_xml(db, platform_name)


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


@router.post("/update/", response_model=errata_schema.ErrataRecord)
async def update_errata_record(
    errata: errata_schema.UpdateErrataRequest,
    db: database.Session = Depends(get_db),
):
    return await errata_crud.update_errata_record(db, errata)


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


@router.post(
    "/update_package_status/",
    response_model=errata_schema.ChangeErrataPackageStatusResponse,
)
async def update_package_status(
    packages: List[errata_schema.ChangeErrataPackageStatusRequest],
    db: database.Session = Depends(get_db),
):
    try:
        return {"ok": bool(await errata_crud.update_package_status(db, packages))}
    except ValueError as e:
        return {"ok": False, "error": e.message}
