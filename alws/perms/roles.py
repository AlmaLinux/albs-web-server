import typing

from pydantic import BaseModel

from alws.perms import actions

__all__ = [
    'Contributor',
    'Manager',
    'Observer',
    'ProductMaintainer',
    'Signer',
    'RolesList',
]


class Role(BaseModel):
    name: str
    actions: typing.List[str]


Manager = Role(
    name='manager',
    actions=[
        actions.ReadTeam.name,
        actions.ReadBuild.name,
        actions.GenKey.name,
        actions.AssignTeamRole.name,
        actions.RemoveFromTeam.name,
        actions.InviteToTeam.name,
        actions.LeaveTeam.name,
        actions.UpdateTeam.name,
        actions.CreateTeam.name,
        actions.DeleteTeam.name,
        actions.CreateBuild.name,
        actions.DeleteBuild.name,
        actions.CreatePlatform.name,
        actions.ReadPlatform.name,
        actions.UpdatePlatform.name,
        actions.DeletePlatform.name,
        actions.CreateProduct.name,
        actions.ReadProduct.name,
        actions.UpdateProduct.name,
        actions.DeleteProduct.name,
        actions.ReadSignKeyInfo.name,
        actions.UpdateTest.name,
        actions.DeleteTest.name,
    ],
)

Contributor = Role(
    name='contributor',
    actions=[
        actions.ReadTeam.name,
        actions.ReadBuild.name,
        actions.LeaveTeam.name,
        actions.CreateTeam.name,
        actions.CreateBuild.name,
        actions.CreateProduct.name,
        actions.ReadProduct.name,
        actions.ReadPlatform.name,
        actions.UpdateTest.name,
    ],
)

Observer = Role(
    name='observer',
    actions=[
        actions.ReadTeam.name,
        actions.ReadBuild.name,
        actions.LeaveTeam.name,
        actions.ReadPlatform.name,
        actions.ReadProduct.name,
    ],
)

ProductMaintainer = Role(
    name='product_maintainer',
    actions=[
        actions.ReadTeam.name,
        actions.GenKey.name,
        actions.ReadBuild.name,
        actions.LeaveTeam.name,
        actions.CreateTeam.name,
        actions.CreateBuild.name,
        actions.CreateProduct.name,
        actions.ReadProduct.name,
        actions.ReadPlatform.name,
        actions.ReleaseBuild.name,
        actions.ReleaseToProduct.name,
        actions.ReadSignKeyInfo.name,
        actions.DeleteRelease.name,
    ],
)

Signer = Role(
    name='signer',
    actions=[
        actions.ReadTeam.name,
        actions.ReadBuild.name,
        actions.LeaveTeam.name,
        actions.CreateTeam.name,
        actions.CreateBuild.name,
        actions.CreateProduct.name,
        actions.ReadProduct.name,
        actions.ReadPlatform.name,
        actions.SignBuild.name,
        actions.ReadSignKeyInfo.name,
        actions.UseSignKey.name,
    ],
)

RolesList = [
    Contributor,
    Observer,
    Manager,
    ProductMaintainer,
    Signer,
]
