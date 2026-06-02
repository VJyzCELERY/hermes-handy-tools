# test_example_function.py
import pytest


def example_addition(a, b):
    """Example function to test."""
    return a + b


def test_example_addition():
    """Test for example_addition."""
    assert example_addition(2, 3) == 5
    assert example_addition(-1, 1) == 0
    assert example_addition(0, 0) == 0


@pytest.mark.parametrize("a, b, result", [(2, 3, 5), (4, 7, 11), (-3, 3, 0), (0, 0, 0)])
def test_example_addition_param(a, b, result):
    """Parametrized test for example_addition."""
    assert example_addition(a, b) == result
