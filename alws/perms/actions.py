import typing

from pydantic import BaseModel

from alws.constants import Permissions

__all__ = [
    'ActionsList',
    'ActionsMaskMapping',
    'Action',
    'CreateBuild',
    'DeleteBuild',
    'ReadBuild',
    'ReleaseBuild',
    'SignBuild',
    'AssignTeamRole',
    'CreateTeam',
    'DeleteTeam',
    'InviteToTeam',
    'LeaveTeam',
    'ReadTeam',
    'RemoveFromTeam',
    'UpdateTeam',
    'CreateProduct',
    'ReadProduct',
    'UpdateProduct',
    'DeleteProduct',
    'ReleaseToProduct',
    'CreatePlatform',
    'ReadPlatform',
    'UpdatePlatform',
    'DeletePlatform',
    'ReadSignKeyInfo',
    'UseSignKey',
    'UpdateTest',
    'DeleteTest',
]


class Action(BaseModel):
    name: str
    description: typing.Optional[str] = None


# Build actions
CreateBuild = Action(
    name='create_build',
    description='Ability to create a build',
)
ReadBuild = Action(
    name='read_build',
    description='Ability to read a build information',
)
SignBuild = Action(
    name='sign_build',
    description='Ability to sign a build',
)
GenKey = Action(
    name='gen_key',
    description='Ability to generate a community sign key',
)
ReleaseBuild = Action(
    name='release_build',
    description='Ability to release a build',
)
DeleteBuild = Action(
    name='delete_build',
    description='Ability to delete a build',
)

# Team actions
CreateTeam = Action(
    name='create_team',
    description='Ability to create a team',
)
ReadTeam = Action(
    name='read_team',
    description='Ability to create a team',
)
UpdateTeam = Action(
    name='update_team',
    description='Ability to update a team information',
)
AssignTeamRole = Action(
    name='assign_team_role',
    description='Ability to assign a team role for a user',
)
InviteToTeam = Action(
    name='invite_into_team',
    description='Ability to invite a user into a team',
)
RemoveFromTeam = Action(
    name='remove_from_team',
    description='Ability to remove a user from a team',
)
LeaveTeam = Action(
    name='leave_team',
    description='Ability for user to leave a team',
)
DeleteTeam = Action(
    name='delete_team',
    description='Ability to delete a team',
)

# Product actions
CreateProduct = Action(
    name='create_product',
    description='Ability to create a product',
)
ReadProduct = Action(
    name='read_product',
    description='Ability to read a product information',
)
UpdateProduct = Action(
    name='update_product',
    description='Ability to update product',
)
DeleteProduct = Action(
    name='delete_product',
    description='Ability to delete a product',
)
ReleaseToProduct = Action(
    name='release_to_product',
    description='Ability to release to a product',
)

# Platform actions
CreatePlatform = Action(
    name='create_platform',
    description='Ability to create a platform',
)
ReadPlatform = Action(
    name='read_platform',
    description='Ability to read a platform information',
)
UpdatePlatform = Action(
    name='update_platform',
    description='Ability to update platform',
)
DeletePlatform = Action(
    name='delete_platform',
    description='Ability to delete a platform',
)
ReadSignKeyInfo = Action(
    name='read_sign_key_info',
    description='Ability to read sign key information',
)
UseSignKey = Action(
    name='use_sign_key',
    description='Ability to use sign key',
)

# Release actions
DeleteRelease = Action(
    name='delete_release',
    description='Ability to delete a release',
)
# Test actions
UpdateTest = Action(
    name='update_test',
    description='Ability to update a test',
)
DeleteTest = Action(
    name='delete_test',
    description='Ability to delete a test',
)


ActionsList = [
    # build actions
    ReadBuild,
    CreateBuild,
    SignBuild,
    GenKey,
    ReleaseBuild,
    DeleteBuild,
    # team actions
    ReadTeam,
    CreateTeam,
    UpdateTeam,
    DeleteTeam,
    AssignTeamRole,
    InviteToTeam,
    RemoveFromTeam,
    LeaveTeam,
    # product actions
    CreateProduct,
    ReadProduct,
    UpdateProduct,
    DeleteProduct,
    ReleaseToProduct,
    # platform actions
    CreatePlatform,
    ReadPlatform,
    UpdatePlatform,
    DeletePlatform,
    # sign key actions
    ReadSignKeyInfo,
    UseSignKey,
    # release actions
    DeleteRelease,
    # test actions
    UpdateTest,
    DeleteTest,
]

ActionsMaskMapping = {
    # build actions mask
    ReadBuild.name: Permissions.READ,
    CreateBuild.name: Permissions.WRITE,
    SignBuild.name: Permissions.WRITE,
    GenKey.name: Permissions.WRITE,
    ReleaseBuild.name: Permissions.WRITE,
    DeleteBuild.name: Permissions.DELETE,
    # team actions mask
    ReadTeam.name: Permissions.READ,
    CreateTeam.name: Permissions.WRITE,
    UpdateTeam.name: Permissions.WRITE,
    DeleteTeam.name: Permissions.DELETE,
    AssignTeamRole.name: Permissions.WRITE,
    InviteToTeam.name: Permissions.WRITE,
    RemoveFromTeam.name: Permissions.WRITE,
    LeaveTeam.name: Permissions.WRITE,
    # product actions mask
    CreateProduct.name: Permissions.WRITE,
    ReadProduct.name: Permissions.READ,
    UpdateProduct.name: Permissions.WRITE,
    DeleteProduct.name: Permissions.DELETE,
    ReleaseToProduct.name: Permissions.WRITE,
    # platform actions mask
    CreatePlatform.name: Permissions.WRITE,
    ReadPlatform.name: Permissions.READ,
    UpdatePlatform.name: Permissions.WRITE,
    DeletePlatform.name: Permissions.DELETE,
    # sign key actions mask
    ReadSignKeyInfo.name: Permissions.READ,
    UseSignKey.name: Permissions.WRITE,
    # release actions mask
    DeleteRelease.name: Permissions.DELETE,
    # test actions mask
    UpdateTest.name: Permissions.WRITE,
    DeleteTest.name: Permissions.DELETE,
}
