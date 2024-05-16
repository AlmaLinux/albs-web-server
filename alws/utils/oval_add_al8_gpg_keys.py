"""
This module allows to add support for multiple GPG keys to the given Oval Composer object.
Basically it converts this
  <oval_definitions>
    <definition>
      <criteria operator="AND">
        <criterion test_ref="oval:org.almalinux.alsa:tst:20237065001"
          comment="tomcat is earlier than 1:9.0.62-27.el8_9" />
        <criterion test_ref="oval:org.almalinux.alsa:tst:20235928002"
          comment="tomcat is signed with AlmaLinux OS 8 key" />
      </criteria>
    </definition>
    definitions>
  </oval_definitions>
  <tests>
    <red-def:rpminfo_test check="at least one" comment="tomcat is signed with AlmaLinux OS 8 key"
      id="oval:org.almalinux.alsa:tst:20235928002" version="636">
      <red-def:object object_ref="oval:org.almalinux.alsa:obj:20235928001" />
      <red-def:state state_ref="oval:org.almalinux.alba:ste:20191992002" />
    </red-def:rpminfo_test>
  </tests>
  <objects>
    <red-def:rpminfo_object id="oval:org.almalinux.alsa:obj:20235928001" version="636">
      <red-def:name>tomcat</red-def:name>
    </red-def:rpminfo_object>
  <objects>
  <states>
    <red-def:rpminfo_state id="oval:org.almalinux.alba:ste:20191992002" version="635">
      <red-def:signature_keyid operation="equals">51d6647ec21ad6ea</red-def:signature_keyid>
    </red-def:rpminfo_state>
  </states>

To this:
<oval_definitions>
  <definition>
    <criteria operator="AND">
      <criterion test_ref="oval:org.almalinux.alsa:tst:20237065001"
        comment="tomcat is earlier than 1:9.0.62-27.el8_9" />
      <criteria operator="OR">
        <criterion test_ref="oval:org.almalinux.alsa:tst:20235928002"
          comment="tomcat is signed with AlmaLinux OS 8 key (51d6647ec21ad6ea)" />
        <criterion test_ref="oval:org.almalinux.alsa:tst:20235928003"
          comment="tomcat is signed with AlmaLinux OS 8 key (2ae81e8aced7258b)" />
      </criteria>
    </criteria>
  <definitions>
</oval_definitions>
<tests>
  <red-def:rpminfo_test check="at least one"
    comment="tomcat is signed with AlmaLinux OS 8 key (51d6647ec21ad6ea)"
    id="oval:org.almalinux.alsa:tst:20235928002" version="636">
    <red-def:object object_ref="oval:org.almalinux.alsa:obj:20235928001" />
    <red-def:state state_ref="oval:org.almalinux.alba:ste:20191992002" />
  </red-def:rpminfo_test>
  <red-def:rpminfo_test check="at least one"
    comment="tomcat is signed with AlmaLinux OS 8 key (2ae81e8aced7258b)"
    id="oval:org.almalinux.alsa:tst:20235928003" version="636">
    <red-def:object object_ref="oval:org.almalinux.alsa:obj:20235928001" />
    <red-def:state state_ref="oval:org.almalinux.alba:ste:20191992003" />
  </red-def:rpminfo_test>
</tests>
<objects>
<red-def:rpminfo_object id="oval:org.almalinux.alsa:obj:20235928001" version="636">
  <red-def:name>tomcat</red-def:name>
</red-def:rpminfo_object>
<objects>
<states>
  <red-def:rpminfo_state id="oval:org.almalinux.alba:ste:20191992002" version="635">
    <red-def:signature_keyid operation="equals">51d6647ec21ad6ea</red-def:signature_keyid>
  </red-def:rpminfo_state>
  <red-def:rpminfo_state id="oval:org.almalinux.alba:ste:20191992003" version="635">
    <red-def:signature_keyid operation="equals">2ae81e8aced7258b</red-def:signature_keyid>
  </red-def:rpminfo_state>
</states>
"""

import itertools
import re
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

try:
    from almalinux.liboval.composer import (
        Composer,
        Definition,
        RpminfoState,
        RpminfoTest,
    )
except ImportError:
    pass

# AL8 GPG keys ids
GPG_KEYS = ['51d6647ec21ad6ea', '2ae81e8aced7258b']


COMMENT_SIGN_PATTERNS = re.compile(r"(\S+) is signed with")


class IdCounter:
    """
    This counter is used for storing the next available ID for tests and states.
    """

    def __init__(self, start_value, step=1):
        """Initialize the counter with a starting value and a step."""
        self.generator = itertools.count(start=start_value, step=step)

    def get_next(self):
        """Return the next counter value."""
        return next(self.generator)


def convert_sign_criterion_to_criteria(
    root_criteria: List[Dict[str, Any]],
    old_to_new_tests_map: Dict[str, Any],
):
    """
    Converts single sign criterion to criteria with multiple sign criterion with new tests.

    Args:
        root_criteria (List[Dict[str, Any]]): The root criteria to be converted.
        old_to_new_tests_map (Dict[str, List[RpminfoTest]]): A mapping of old test to new tests.

    Returns:
        List[Dict[str, Any]]: The converted criteria.

    """

    # Recursive function to traverse and update the tree
    def traverse_criteria(criteria_list):
        for criteria in criteria_list:
            # Recursively traverse deeper criteria lists if they exist
            if 'criteria' in criteria:
                traverse_criteria(criteria['criteria'])
            # Check if this criteria contains the specified criterion and append if found
            if 'criterion' in criteria:
                # Iterate over a copy of the list
                for crit in list(criteria['criterion']):
                    match = COMMENT_SIGN_PATTERNS.search(crit['comment'])
                    if not match:
                        continue
                    new_criteria = {
                        "criteria": [],
                        "operator": "OR",
                        "criterion": [
                            {'ref': test.test_id, 'comment': test.comment}
                            for test in old_to_new_tests_map[crit['ref']]
                        ],
                    }
                    criteria['criteria'].append(new_criteria)
                    # Remove the criterion from the original list
                    criteria['criterion'].remove(crit)
                    # No return here; continue to process all criteria

    fixed_criteria = deepcopy(root_criteria)
    for c in fixed_criteria:
        traverse_criteria([c])
    return fixed_criteria


def get_first_available_ids(oval) -> Tuple[int, int]:
    """
    Returns the first available test ID and state ID in the given Composer object.

    Parameters:
    oval (Composer): The Composer object containing tests and states.

    Returns:
    Tuple[int, int]: A tuple containing the first available test ID and state ID.
    """
    max_test_id = max(int(test.test_id.split(":")[-1]) for test in oval.iter_tests())
    max_state_id = max(
        int(state.state_id.split(":")[-1]) for state in oval.iter_states()
    )
    return max_test_id + 1, max_state_id + 1


def generate_gpg_keys_states(states_counter, original_state) -> List:
    """
    Generate GPG keys states original state.

    Args:
      states_counter (IdCounter): An instance of IdCounter used to generate unique state IDs.
      original_state (RpminfoState): The original state to base the generated states on.

    Returns:
      List[RpminfoState]: A list of RpminfoState objects representing the generated GPG keys states.
    """
    original_state_dict = original_state.as_dict()
    state_id_prefix = ":".join(original_state_dict['id'].split(":")[:-1])
    states = []
    for key in GPG_KEYS:
        attrs = original_state_dict.copy()
        attrs['id'] = f"{state_id_prefix}:{str(states_counter.get_next())}"
        attrs['signature_keyid'] = key
        rpminfo_state = RpminfoState.from_dict(attrs)
        states.append(rpminfo_state)
    return states


def get_new_tests_states(
    oval,
) -> Tuple[List, List, Dict[str, List]]:
    """
    Generates new tests and states based on the given Oval Composer.

    Args:
        oval (Composer): The Oval Composer object containing the original tests and states.

    Returns:
        Tuple[List[RpminfoTest], List[RpminfoState], Dict[str, List[RpminfoTest]]]:
        A tuple containing the new tests,
        new states, and a mapping of old test IDs to new test lists.
    Raises:
        AssertionError: If the original GPG state is not found.
    """
    # getting starting values for ids
    test_id_start_from, state_id_start_from = get_first_available_ids(oval)

    # Preparing new states
    states_counter = IdCounter(state_id_start_from)
    original_gpg_state: Optional[RpminfoState] = None
    for state in oval.iter_states():
        if isinstance(state, RpminfoState) and state.signature_keyid:
            original_gpg_state = state
            break
    assert original_gpg_state, "Original GPG state not found"
    gpg_keys_states = generate_gpg_keys_states(states_counter, original_gpg_state)
    new_states = list(oval.iter_states()) + gpg_keys_states

    # Preparing new tests
    tests_counter = IdCounter(test_id_start_from)
    # <old_test_id>: [new_test1, new_test2, ...]
    old_to_new_test_map: Dict[str, List[RpminfoTest]] = {}
    new_tests: List[RpminfoTest] = []
    for test in oval.iter_tests():
        if type(RpminfoTest) and 'is signed with' in test.comment:
            # we need to replace this test new tests for new keys
            test_as_dict = test.as_dict()
            added_tests: List[RpminfoTest] = []
            test_id_prefix = ":".join(test_as_dict['id'].split(":")[:-1])
            for state in gpg_keys_states:
                attrs = test_as_dict.copy()
                attrs['comment'] = (
                    f"{test_as_dict['comment']} ({state.signature_keyid})"
                )
                attrs['id'] = f"{test_id_prefix}:{str(tests_counter.get_next())}"
                attrs['state_ref'] = state.state_id
                added_test = RpminfoTest.from_dict(attrs)
                new_tests.append(added_test)
                added_tests.append(added_test)
            old_to_new_test_map[test.test_id] = added_tests
        else:
            # no need to replace this test
            new_tests.append(test)
    return new_tests, new_states, old_to_new_test_map


def add_multiple_gpg_keys_to_oval(oval):
    """
    Adds support for multiple GPG keys to the given Oval Composer object.

    Args:
        oval (Composer): The Oval Composer object to add the GPG keys to.
    Returns:
        Composer: The Oval Composer object with the added GPG keys.
    """
    new_oval = Composer()
    new_oval.generator = oval.generator
    new_tests, new_states, old_to_new_tests_map = get_new_tests_states(oval)
    for old_definition in oval.iter_definitions():
        definition_as_dict = old_definition.as_dict()
        definition_as_dict['criteria'] = convert_sign_criterion_to_criteria(
            definition_as_dict['criteria'], old_to_new_tests_map
        )
        new_definition = Definition.from_dict(definition_as_dict)
        new_oval.append_object(new_definition)
    for new_test in new_tests:
        new_oval.append_object(new_test)
    for obj in oval.iter_objects():
        new_oval.append_object(obj)
    for new_state in new_states:
        new_oval.append_object(new_state)
    for variables in oval.iter_variables():
        new_oval.append_object(variables)
    return new_oval
