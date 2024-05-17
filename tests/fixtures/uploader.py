import pytest

from alws import models
from alws.utils.modularity import IndexWrapper
from alws.utils.uploader import MetadataUploader
from tests.test_utils.pulp_utils import get_repo_href


@pytest.fixture
def upload_rpm_modules(monkeypatch):
    async def func(
        _,
        module_content: str,
        dry_run: bool = False,
    ):
        db_modules = []
        module_hrefs = []
        defaults_hrefs = []
        _index = IndexWrapper.from_template(module_content)

        for module in _index.iter_modules():
            pulp_href = get_repo_href()
            db_module = models.RpmModule(
                name=module.name,
                stream=module.stream,
                context=module.context,
                arch=module.arch,
                version=str(module.version),
                pulp_href=pulp_href,
            )
            db_modules.append(db_module)
            module_hrefs.append(pulp_href)
        return db_modules, module_hrefs, defaults_hrefs

    monkeypatch.setattr(MetadataUploader, "upload_rpm_modules", func)
