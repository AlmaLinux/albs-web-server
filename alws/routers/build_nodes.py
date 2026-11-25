import typing

from fastapi import APIRouter, Depends
from fastapi_sqla import AsyncSessionDependency
from sqlalchemy.ext.asyncio import AsyncSession

from alws.auth import get_current_superuser
from alws.crud import build_nodes
from alws.dependencies import get_async_db_key
from alws.schemas import build_node_schema

# The registry is a part of the administration: node names, their hosts
# resources and tasks are shown to superusers only
router = APIRouter(
    prefix='/build_nodes',
    tags=['build_nodes'],
    dependencies=[Depends(get_current_superuser)],
)


@router.get('/', response_model=typing.List[build_node_schema.BuildNode])
async def get_build_nodes(
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await build_nodes.get_build_nodes(db)


# Has to be declared before /{node_id}
@router.get(
    '/queue',
    response_model=typing.List[build_node_schema.BuildNodesQueue],
)
async def get_build_nodes_queue(
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await build_nodes.get_build_nodes_queue(db)


@router.get(
    '/{node_id}',
    response_model=build_node_schema.BuildNodeDetails,
)
async def get_build_node(
    node_id: int,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await build_nodes.get_build_node(db, node_id)


@router.patch(
    '/{node_id}',
    response_model=build_node_schema.BuildNode,
)
async def update_build_node(
    node_id: int,
    payload: build_node_schema.BuildNodeUpdate,
    db: AsyncSession = Depends(AsyncSessionDependency(key=get_async_db_key())),
):
    return await build_nodes.update_build_node(db, node_id, payload)
