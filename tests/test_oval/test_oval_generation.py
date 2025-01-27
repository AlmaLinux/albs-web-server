from unittest import TestCase

from alws.crud.errata import new_errata_records_to_oval
from almalinux.liboval.composer import Composer


def test_new_errata_records_to_oval(new_errata_records_samples, oval_sample):
    oval_string = new_errata_records_to_oval(new_errata_records_samples)

    # uncomment to update oval sample xml file
    # from pathlib import Path
    # dst_path = Path(__file__).parents[1] / 'samples/test_oval.xml'
    # with dst_path.open('wb') as f:
    #     f.write(oval_string)

    generated_oval_dict = Composer.load_from_string(oval_string).as_dict()
    expected_oval_dict = Composer.load_from_string(oval_sample).as_dict()


    TestCase().assertDictEqual(generated_oval_dict, expected_oval_dict)
