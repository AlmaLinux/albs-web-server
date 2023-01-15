import unittest

from alws.schemas import build_node_schema


class TestBuildNodeSchema(unittest.TestCase):
    def test_is_debuginfo(self):
        test_artifact = build_node_schema.BuildDoneArtifact(
            name="test-debuginfo-1",
            type="build_log",
            href="http://127.0.0.1:8080/test_example.com",
            sha256="6f9ee4d51eeb618dc21878f20ce8f7b2cdefb56c0071b058b48a1d4748c10987",
            cas_hash=None,
        )
        message = "is_debuginfo don't work with correct data"
        self.assertTrue(test_artifact.is_debuginfo, message)

    def test_false_is_debuginfo(self):
        test_artifact = build_node_schema.BuildDoneArtifact(
            name="test",
            type="build_log",
            href="http://127.0.0.1:8080/test_example.com",
            sha256="ab1e06f801c80dea646f6a7dcf5e5ca7d829ed0b00144aed0670c512076ec3fc",
            cas_hash=None,
        )
        message = "is_debuginfo don't work with incorrect data"
        self.assertFalse(test_artifact.is_debuginfo, message)
