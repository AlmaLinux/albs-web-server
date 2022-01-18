import typing
import logging

import aiohttp.client_exceptions
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)

from alws import database
from alws.config import settings
from alws.crud import (
    build as build_crud,
    build_node,
    platform as platform_crud
)
from alws.dependencies import get_db, JWTBearer
from alws.errors import DataNotFoundError
from alws.schemas import build_schema
from alws.utils.gitea import download_modules_yaml, GiteaClient
from alws.constants import BuildTaskRefType
from alws.utils.modularity import ModuleWrapper, get_modified_refs_list


router = APIRouter(
    prefix='/builds',
    tags=['builds'],
    dependencies=[Depends(JWTBearer())]
)


@router.post('/', response_model=build_schema.Build)
async def create_build(
            build: build_schema.BuildCreate,
            user: dict = Depends(JWTBearer()),
            db: database.Session = Depends(get_db)
        ):
    db_build = await build_crud.create_build(
        db, build, user['identity']['user_id'])
    return db_build


@router.get('/', response_model=typing.Union[
    typing.List[build_schema.Build], build_schema.BuildsResponse])
async def get_builds_per_page(
    request: Request,
    pageNumber: int,
    db: database.Session = Depends(get_db),
):
    search_params = build_schema.BuildSearch(**request.query_params)
    return await build_crud.get_builds(
        db=db,
        page_number=pageNumber,
        search_params=search_params,
    )


@router.post('/get_module_preview/',
             response_model=build_schema.ModulePreview)
async def get_module_preview(
    module_request: build_schema.ModulePreiewRequest,
    db: database.Session = Depends(get_db)
):
    result = []
    gitea_client = GiteaClient(
        settings.gitea_host,
        logging.getLogger(__name__)
    )
    template = await download_modules_yaml(
        module_request.ref.url,
        module_request.ref.git_ref,
        BuildTaskRefType.to_text(module_request.ref.ref_type)
    )
    module = ModuleWrapper.from_template(
        template,
        name=module_request.ref.git_repo_name,
        stream=module_request.ref.module_stream_from_ref()
    )
    platform = await platform_crud.get_platform(
        db, module_request.platform_name
    )
    platform_prefix_list = platform.modularity['git_tag_prefix']
    platform_packages_git = platform.modularity['packages_git']
    modified_list = await get_modified_refs_list(
        platform.modularity['modified_packages_url']
    )
    for component_name, _ in module.iter_components():
        ref_prefix = platform_prefix_list['non_modified']
        if component_name in modified_list:
            ref_prefix = platform_prefix_list['modified']
        git_ref = f'{ref_prefix}-stream-{module.stream}'
        exist = True
        commit_id = ''
        try:
            response = await gitea_client.get_branch(
                f'rpms/{component_name}', git_ref
            )
            commit_id = response['commit']['id']
        except aiohttp.client_exceptions.ClientResponseError as e:
            if e.status == 404:
                exist = False
        result.append(build_schema.ModuleRef(
            url=f'{platform_packages_git}{component_name}.git',
            git_ref=git_ref,
            exist=exist,
            mock_options={
                'definitions': {
                    k: v for k, v in module.iter_mock_definitions()
                }
            },
            ref_type=BuildTaskRefType.GIT_BRANCH
        ))
        module.set_component_ref(component_name, commit_id)
    return build_schema.ModulePreview(
        refs=result,
        module_name=module.name,
        module_stream=module.stream,
        modules_yaml=module.render()
    )


@router.get('/{build_id}/', response_model=build_schema.Build)
async def get_build(build_id: int, db: database.Session = Depends(get_db)):
    db_build = await build_crud.get_builds(db, build_id)
    if db_build is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Build with {build_id=} is not found'
        )
    return db_build


@router.patch('/{build_id}/restart-failed', response_model=build_schema.Build)
async def restart_failed_build_items(build_id: int,
                                     db: database.Session = Depends(get_db)):
    return await build_node.update_failed_build_items(db, build_id)


@router.delete('/{build_id}/remove', status_code=204)
async def remove_build(build_id: int, db: database.Session = Depends(get_db)):
    try:
        result = await build_crud.remove_build_job(db, build_id)
    except DataNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Build with {build_id=} is not found',
        )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Build with {build_id=} is released',
        )
    return result
