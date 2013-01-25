import datetime
from decimal import Decimal
import unittest
# XXX not generic import
from libraries.aetycoon import value_to_pickle


class PickleValueTests(unittest.TestCase):
  def assertRaisesWithMessage(self, exc_class, msg, func, *args, **kwargs):
    try:
      func(*args, **kwargs)
      assert False, 'No exception raised.'
    except Exception as inst:
      if isinstance(inst, AssertionError):
        raise
      self.assertEquals(inst.__class__, exc_class)
      self.assertEquals(inst.message, msg)

  def test_eval_simple_values(self):
    values = [
      ('True', True),
      ('False', False),
      ('{"a": "b"}', {'a': 'b'}),
      ('["item1", 2]', ['item1', 2]),
      ('datetime.datetime(2012, 12, 12, 12, 12)', datetime.datetime(2012, 12, 12, 12, 12)),
      ('Decimal("12.99")', Decimal('12.99')),
    ]
    for str_value, expected in values:
      self.assertEquals(value_to_pickle(str_value), expected)

  def test_eval_syntax_error(self):
    values = [
      ('True"', 'Invalid syntax: EOL while scanning string literal'),
      ('{"str": secret_value}', "You tried to use an unsupported type. (NameError: name 'secret_value' is not defined)"),
      ('{"str": datetime(2012, 12, 12, 12)}', "Maybe you tried to use datetime instead of datetime.datetime?"),
      ('Decimal.decimal("2.12")', "Attribute not found: type object 'Decimal' has no attribute 'decimal'"),
      ('Decimal', "Pickle value is not allowed to be a class."),
      ('1 / 0', "integer division or modulo by zero"),
      ('import helpers.utils\nhelpers.utils.random_string(3)', "Invalid syntax: invalid syntax"),
      ('import pickle\n3', "Invalid syntax: invalid syntax"),
      ('[][1]', "list index out of range"),
      ('{"b": "c"}["a"]', "Key error: a"),
      ('  \t\n  {}', "Invalid syntax: unexpected indent"),
    ]
    for str_value, expected in values:
      func = lambda: value_to_pickle(str_value)
      self.assertRaisesWithMessage(ValueError, expected, func)
