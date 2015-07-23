import unittest
from opendeep.data.stream.modifystream import ModifyStream

class TestModifystream(unittest.TestCase):

    def setUp(self):
        pass

    def testModify(self):
        testStream = [
            "1",
            "2",
            "3",
        ]
        answer = [1, 2, 3]

        ms = ModifyStream(testStream, lambda s: int(s))
        for idx, elem in enumerate(ms):
            assert elem == answer[idx], "Expected %d, found %s" % (answer[idx], str(elem))

    def tearDown(self):
        pass


if __name__ == '__main__':
    unittest.main()
