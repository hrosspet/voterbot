import unittest
from steevebase.model import generator


class TestGenerator(unittest.TestCase):
    def test_one_hot_encode_post(self):
        import numpy
        numpy.random.seed(10)

        output = generator.one_hot_encode_post('aabbb', 'aaaaabbb  bbbb cccc aaaa',
                                               {'a': 1, 'b': 2, 'c': 3, ' ': 4, '+': 5},
                                               10, 6)
        expected = numpy.array([[0., 1., 0., 0., 0., 0.],
                                [0., 1., 0., 0., 0., 0.],
                                [0., 0., 1., 0., 0., 0.],
                                [0., 0., 1., 0., 0., 0.],
                                [0., 0., 1., 0., 0., 0.],
                                [0., 0., 0., 0., 0., 1.],
                                [0., 0., 0., 0., 1., 0.],
                                [0., 0., 1., 0., 0., 0.],
                                [0., 0., 1., 0., 0., 0.],
                                [0., 0., 1., 0., 0., 0.]])
        numpy.testing.assert_equal(output, expected)
