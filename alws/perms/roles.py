import typing

from pydantic import BaseModel

from alws.perms import actions


__all__ = [
    'Contributor',
    'Manager',
    'Observer',
    'PlatformMaintainer',
    'ProductMaintainer',
    'Signer',
]


class Role(BaseModel):
    name: str
    actions: typing.Iterable[str]


Manager = Role(
    name='manager',
    actions=[
        actions.ReadTeam.name,
        actions.ReadBuild.name,
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
    ]
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
    ]
)

Observer = Role(
    name='observer',
    actions=[
        actions.ReadTeam.name,
        actions.ReadBuild.name,
        actions.LeaveTeam.name,
        actions.ReadPlatform.name,
        actions.ReadProduct.name,
    ]
)

ProductMaintainer = Role(
    name='product_maintainer',
    actions=[
        actions.ReadTeam.name,
        actions.ReadBuild.name,
        actions.LeaveTeam.name,
        actions.CreateTeam.name,
        actions.CreateBuild.name,
        actions.CreateProduct.name,
        actions.ReadProduct.name,
        actions.ReadPlatform.name,
        actions.ReleaseToProduct.name,
    ]
)

PlatformMaintainer = Role(
    name='platform_maintainer',
    actions=[
        actions.ReadTeam.name,
        actions.ReadBuild.name,
        actions.LeaveTeam.name,
        actions.CreateTeam.name,
        actions.CreateBuild.name,
        actions.CreateProduct.name,
        actions.ReadProduct.name,
        actions.ReadPlatform.name,
        actions.ReleaseToPlatform.name,
    ]
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
    ]
)
