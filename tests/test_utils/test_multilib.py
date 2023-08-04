import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from alws.utils.multilib import MultilibProcessor
from alws.utils.modularity import IndexWrapper
from alws.dramatiq.build import _start_build
from alws import models
from alws.config import settings
from alws.utils.beholder_client import BeholderClient

@pytest.mark.anyio
async def test_update_module_index(
    session: AsyncSession,
    base_platform: models.Platform,
    base_product: models.Product,
    modules_yaml_virt: bytes,
    build_virt_done,
):
    beholder_client = BeholderClient(
        settings.beholder_host, token=settings.beholder_token
    )

    module_index_with_artifacts = IndexWrapper.from_template(
        modules_yaml_virt.decode()
    )
    #settings.package_beholder_enabled = True

    #build_task = build_virt_done.tasks[0]
    modules_yaml = ''
    with open('/code/modules.yaml', 'r') as file:
        modules_yaml = file.read()

    module_index = IndexWrapper.from_template(
        modules_yaml
    )
    for _module in module_index.iter_modules():
        module_with_artifacts = module_index_with_artifacts.get_module(
            name=_module.name,
            stream=_module.stream
        )
        artifacts = module_with_artifacts.get_rpm_artifacts()

        new_artifacts = _module.get_rpm_artifacts()
        assert new_artifacts == artifacts
