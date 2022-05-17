import re
import typing
from tap import parser

import hawkey

from alws.constants import TestCaseStatus


__all__ = [
    'clean_module_tag',
    'get_clean_distr_name',
    'parse_git_ref',
    'parse_tap_output',
    'tap_set_status',
    'slice_list',
]


def slice_list(source_list: list,
               max_len: int) -> typing.Generator[typing.List[str], None, None]:
    return (
        source_list[i:i + max_len]
        for i in range(0, len(source_list), max_len)
    )


def clean_module_tag(tag: str):
    clean_tag = re.sub(r'\.alma.*$', '', tag)
    raw_part = re.search(r'\.module.*', clean_tag).group()
    latest = re.search(r'\.\d*$', raw_part)
    result = re.sub(r'\.module.*', '', clean_tag)
    if latest is not None:
        result += latest.group()
    return result


def get_clean_distr_name(distr_name: str) -> str:
    clean_distr_name = re.search(
        r'^(?P<dist_name>[a-z]+)', distr_name, re.IGNORECASE,
    ).groupdict().get('dist_name', '')
    return clean_distr_name


def parse_git_ref(pattern: str, git_ref: str):
    re_pattern = re.compile(pattern)
    match = re_pattern.search(git_ref)
    if match:
        return match.groups()[-1]
    else:
        return
    

def parse_rpm_nevra(rpm_name: str):
    clean_rpm_name = re.sub('.rpm$', '', rpm_name)
    hawkey_nevra = hawkey.split_nevra(clean_rpm_name)


def parse_tap_output(text: bytes) -> list:
    """
    Parses TAP test output and returns list of TAP-formatted entities.
    Returns list of dicts with detailed status report for each test in file.

    Parameters
    ----------
    text : bytes
        Test output

    Returns
    -------
    list

    """
    try:
        text = text.decode('utf8')
    except UnicodeDecodeError:
        text = text.decode('utf8', 'replace')
    prepared_text = text.replace("\r\n", "\n")
    tap_parser = parser.Parser()
    try:
        raw_data = list(tap_parser.parse_text(prepared_text))
    except Exception:
        return []

    def get_diagnostic(tap_item):
        diagnostics = []
        index = raw_data.index(tap_item) + 1
        while index < len(raw_data) and \
                raw_data[index].category == "diagnostic":
            diagnostics.append(raw_data[index].text)
            index += 1
        return u"\n".join(diagnostics)

    tap_output = []
    if any([item.category != "unknown" for item in raw_data]):
        for test_result in raw_data:
            if test_result.category == "test":
                test_case = {}
                test_name = test_result.description
                if not test_name:
                    test_name = test_result.directive.text
                test_case["test_name"] = test_name
                if test_result.todo:
                    test_case["status"] = TestCaseStatus.TODO
                elif test_result.skip:
                    test_case["status"] = TestCaseStatus.SKIPPED
                elif test_result.ok:
                    test_case["status"] = TestCaseStatus.DONE
                else:
                    test_case["status"] = TestCaseStatus.FAILED
                test_case["diagnostic"] = get_diagnostic(test_result)
                tap_output.append(test_case)
            else:
                continue
    return tap_output


def tap_set_status(tap_results):
    """
    Set status for test TAP logs

    Parameters
    ----------
    tap_results : list of dicts
        Results of testing TAP parsing
    Returns
    -------
    bool
        True if all tests have passed, False otherwise

    """
    conditions = [item["status"] == TestCaseStatus.FAILED for item in tap_results]
    return False if any(conditions) else True
