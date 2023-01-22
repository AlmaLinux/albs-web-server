import unittest

from alws.utils.parsing import parse_tap_output, tap_set_status


class TapParseTest(unittest.TestCase):
    skip_tap = {
        "log": "1..3\r\nok 1 # skip (lve-utils-debuginfo is debuginfo package) lve-utils-debuginfo shared library dependencies installed\r\nok 2 # skip (lve-utils-debuginfo is debuginfo package) lve-utils-debuginfo files are correctly installed\r\nok 3 # skip (lve-utils-debuginfo is debuginfo package) lve-utils-debuginfo shared library doesn't contain trailing ':' in RPATH\r\n\nRet code: 0",
        "tap_results": [
            {
                "status": 4,
                "test_name": "skip (lve-utils-debuginfo is debuginfo package) lve-utils-debuginfo shared library dependencies installed",
                "diagnostic": "",
            },
            {
                "status": 4,
                "test_name": "skip (lve-utils-debuginfo is debuginfo package) lve-utils-debuginfo files are correctly installed",
                "diagnostic": "",
            },
            {
                "status": 4,
                "test_name": "skip (lve-utils-debuginfo is debuginfo package) lve-utils-debuginfo shared library doesn't contain trailing ':' in RPATH",
                "diagnostic": "",
            },
        ],
    }
    done_tap = {
        "log": "1..5\r\nok 1 run 'lvectl list' check present all containers \r\nok 2 check do not affect reseller's cpu & io limit\r\nok 3 check packages should affect user same name as reseller\r\nok 4 admin packages should affect users\r\nok 5 admin packages should affect reseller's users\r\n\nRet code: 0",
        "tap_results": [
            {
                "status": 2,
                "test_name": "run 'lvectl list' check present all containers",
                "diagnostic": "",
            },
            {
                "status": 2,
                "test_name": "check do not affect reseller's cpu & io limit",
                "diagnostic": "",
            },
            {
                "status": 2,
                "test_name": "check packages should affect user same name as reseller",
                "diagnostic": "",
            },
            {
                "status": 2,
                "test_name": "admin packages should affect users",
                "diagnostic": "",
            },
            {
                "status": 2,
                "test_name": "admin packages should affect reseller's users",
                "diagnostic": "",
            },
        ],
    }
    fail_tap = {
        "log": "FAIL:\n1..5\r\nnot ok 1 run 'lvectl list' check present all containers \r\n# (from function `present_in_lvectl' in file src/assertions.bash, line 129,\r\n#  in test file 33-1_reseller_limits.bats, line 36)\r\n#   `present_in_lvectl 20001 20002 20003 20004 10001 10002 10003 10004 10006 10007' failed\r\n# /tmp/bats.17995.src: line 20: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 21: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 22: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 23: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 24: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 25: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 26: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 27: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 28: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 29: /bin/lve_suwrapper: No such file or directory\r\n# The record(s) with ID 20001,20002,20003,20004,10001,10002,10003,10004,10006,10007 must be present in the output: \r\n#       ID   SPEED    PMEM    VMEM      EP   NPROC      IO    IOPS\r\n#  default      50   1024M   1024M      20       0    1024    1024\r\n#    limit       0      0K      0K       0       0       0       0\r\n# \r\n# but 10004,10006,10007,10001,10002,10003,20004,20003,20002,20001 id(s) not present\r\nok 2 run 'lvectl set-reseller --all' enable limits to all resellers \r\nnot ok 3 run 'lvectl list' check present all containers after 'lvectl set-reseller --all' \r\n# (from function `present_in_lvectl' in file src/assertions.bash, line 129,\r\n#  in test file 33-1_reseller_limits.bats, line 51)\r\n#   `present_in_lvectl 20001 20002 20003 20004 10001 10002 10003 10004 10006 10007' failed\r\n# /tmp/bats.17995.src: line 20: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 21: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 22: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 23: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 24: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 25: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 26: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 27: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 28: /bin/lve_suwrapper: No such file or directory\r\n# /tmp/bats.17995.src: line 29: /bin/lve_suwrapper: No such file or directory\r\n# The record(s) with ID 20001,20002,20003,20004,10001,10002,10003,10004,10006,10007 must be present in the output: \r\n#       ID   SPEED    PMEM    VMEM      EP   NPROC      IO    IOPS\r\n#  default      50   1024M   1024M      20       0    1024    1024\r\n#    limit       0      0K      0K       0       0       0       0\r\n# \r\n# but 10004,10006,10007,10001,10002,10003,20004,20003,20002,20001 id(s) not present\r\nok 4 run 'lvectl list-reseller' check present resellers containers \r\nok 5 run 'lvectl list-reseller --with-name' check present resellers containers",
        "tap_results": [
            {
                "status": 1,
                "test_name": "run 'lvectl list' check present all containers",
                "diagnostic": "# (from function `present_in_lvectl' in file src/assertions.bash, line 129,\n#  in test file 33-1_reseller_limits.bats, line 36)\n#   `present_in_lvectl 20001 20002 20003 20004 10001 10002 10003 10004 10006 10007' failed\n# /tmp/bats.17995.src: line 20: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 21: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 22: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 23: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 24: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 25: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 26: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 27: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 28: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 29: /bin/lve_suwrapper: No such file or directory\n# The record(s) with ID 20001,20002,20003,20004,10001,10002,10003,10004,10006,10007 must be present in the output:\n#       ID   SPEED    PMEM    VMEM      EP   NPROC      IO    IOPS\n#  default      50   1024M   1024M      20       0    1024    1024\n#    limit       0      0K      0K       0       0       0       0\n#\n# but 10004,10006,10007,10001,10002,10003,20004,20003,20002,20001 id(s) not present",
            },
            {
                "status": 2,
                "test_name": "run 'lvectl set-reseller --all' enable limits to all resellers",
                "diagnostic": "",
            },
            {
                "status": 1,
                "test_name": "run 'lvectl list' check present all containers after 'lvectl set-reseller --all'",
                "diagnostic": "# (from function `present_in_lvectl' in file src/assertions.bash, line 129,\n#  in test file 33-1_reseller_limits.bats, line 51)\n#   `present_in_lvectl 20001 20002 20003 20004 10001 10002 10003 10004 10006 10007' failed\n# /tmp/bats.17995.src: line 20: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 21: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 22: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 23: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 24: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 25: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 26: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 27: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 28: /bin/lve_suwrapper: No such file or directory\n# /tmp/bats.17995.src: line 29: /bin/lve_suwrapper: No such file or directory\n# The record(s) with ID 20001,20002,20003,20004,10001,10002,10003,10004,10006,10007 must be present in the output:\n#       ID   SPEED    PMEM    VMEM      EP   NPROC      IO    IOPS\n#  default      50   1024M   1024M      20       0    1024    1024\n#    limit       0      0K      0K       0       0       0       0\n#\n# but 10004,10006,10007,10001,10002,10003,20004,20003,20002,20001 id(s) not present",
            },
            {
                "status": 2,
                "test_name": "run 'lvectl list-reseller' check present resellers containers",
                "diagnostic": "",
            },
            {
                "status": 2,
                "test_name": "run 'lvectl list-reseller --with-name' check present resellers containers",
                "diagnostic": "",
            },
        ],
    }

    def test_skip(self):
        res_skip = parse_tap_output(str.encode(self.skip_tap["log"]))
        self.assertTrue(type(res_skip) == list)
        self.assertEqual(res_skip, self.skip_tap["tap_results"])
        self.assertEqual(True, tap_set_status(res_skip))

    def test_done(self):
        res_skip = parse_tap_output(str.encode(self.done_tap["log"]))
        self.assertTrue(type(res_skip) == list)
        self.assertEqual(res_skip, self.done_tap["tap_results"])
        self.assertEqual(True, tap_set_status(res_skip))

    def test_fail(self):
        res_skip = parse_tap_output(str.encode(self.fail_tap["log"]))
        self.assertTrue(type(res_skip) == list)
        self.assertEqual(res_skip, self.fail_tap["tap_results"])
        self.assertEqual(False, tap_set_status(res_skip))
