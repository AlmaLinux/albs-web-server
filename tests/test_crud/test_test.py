from alws.crud.test import get_logs_format


class TestGetLogsFormat:

    text_logs = b"Exit code: 0\nStdout:\n\n\nPLAY [Prepare environment] *****************************************************\n\nTASK [Gathering Facts] *********************************************************\nok: [docker_29ed7aff-ad88-453b-9048-167a30fc99b7]\n\nTASK [Enable module] ***********************************************************\nskipping: [docker_29ed7aff-ad88-453b-9048-167a30fc99b7]\n\nTASK [Install package] *********************************************************\nchanged: [docker_29ed7aff-ad88-453b-9048-167a30fc99b7]\n\nTASK [Install package] *********************************************************\nskipping: [docker_29ed7aff-ad88-453b-9048-167a30fc99b7]\n\nPLAY RECAP *********************************************************************\ndocker_29ed7aff-ad88-453b-9048-167a30fc99b7 : ok=2    changed=1    unreachable=0    failed=0    skipped=2    rescued=0    ignored=0   \n\nStderr:\n\n[WARNING]: Platform linux on host docker_29ed7aff-ad88-453b-9048-167a30fc99b7\nis using the discovered Python interpreter at /usr/bin/python3.6, but future\ninstallation of another Python interpreter could change this. See https://docs.\nansible.com/ansible/2.9/reference_appendices/interpreter_discovery.html for\nmore information.\n"
    tap_logs = b"Exit code: 0\nStdout:\n\n1..4\nok 1 tests/test_package_is_correct.py::test_package_is_installed[local]\nok 2 tests/test_package_is_correct.py::test_all_package_files_exist[local]\nok 3 tests/test_package_is_correct.py::test_binaries_have_all_dependencies[local]\nok 4 tests/test_package_is_correct.py::test_check_rpath_is_correct[local]\n"

    def test_text_logs(self):
        test_log_format = get_logs_format(self.text_logs)
        assert "text" == test_log_format

    def test_tap_logs(self):
        test_log_format = get_logs_format(self.tap_logs)
        assert "tap" == test_log_format
