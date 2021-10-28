import unittest

from alws.schemas import build_node_schema


class TestBuildNodeSchema(unittest.TestCase):
    
    def test_is_debuginfo(self):
        test_BuildDoneArtifact = build_node_schema.BuildDoneArtifact(
            name='test-debuginfo-1',
            type='build_log',
            href='http://127.0.0.1:8080/test_example.com'
        )
        message = "is_debuginfo don't work with correct data"
        self.assertTrue(test_BuildDoneArtifact.is_debuginfo, message)

    def test_false_is_debuginfo(self):
        test_BuildDoneArtifact = build_node_schema.BuildDoneArtifact(
            name='test-debuginfo',
            type='build_log',
            href='http://127.0.0.1:8080/test_example.com'
        )
        message = "is_debuginfo don't work with incorrect data"
        self.assertFalse(test_BuildDoneArtifact.is_debuginfo, message)
