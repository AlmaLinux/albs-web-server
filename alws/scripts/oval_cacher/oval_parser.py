from almalinux.liboval.composer import Composer


def oval_to_dict(oval_file) -> dict:
    return Composer.load_from_file(oval_file).as_dict()
