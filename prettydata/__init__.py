def pretty_dict(d, indent=0, nest_level=1):
  '''List-format string output to display a dict in a readable format.'''
  if not d:
    yield '{}'
    return
  sorted_items = d.items()
  sorted_items.sort(key=lambda x: x[0])

  yield '{\n'
  first = True
  for k, v in sorted_items:
    if not first:
      yield ",\n"
    else:
      first = False
    if isinstance(k, unicode):
      try:
        repr_k = repr(str(k))
      except UnicodeEncodeError:
        repr_k = repr(k)
    else:
      repr_k = repr(k)
    yield '{indent}{key}: '.format(indent=' ' * indent * nest_level, key=repr_k)
    yield _pretty_merge_value(v, indent, nest_level)
  yield "\n"
  yield ' ' * indent * (nest_level - 1) + '}'


def pretty_list(l, indent=0, nest_level=1):
  '''List-format string output to display a list or tuple in a readable format.'''
  if not l:
    yield '[]' if isinstance(l, list) else 'tuple()'
    return
  if isinstance(l, list):
    yield '[\n'
  else:
    yield '(\n'
  first = True
  for v in l:
    if not first:
      yield ",\n"
    else:
      first = False
    yield ' ' * indent * nest_level
    yield _pretty_merge_value(v, indent, nest_level)
  yield "\n"
  yield ' ' * indent * (nest_level - 1)
  if isinstance(l, list):
    yield ']'
  else:
    yield ')'


def _pretty_merge_value(v, indent, nest_level):
  '''Local use to merge known vaues into a pretty output.'''
  if isinstance(v, dict):
    yield pretty_dict(v, indent=indent, nest_level=nest_level + 1)
  elif isinstance(v, (list, tuple)):
    yield pretty_list(v, indent=indent, nest_level=nest_level + 1)
  elif isinstance(v, unicode):  # Take out the u'' when unnecessary
    try:
      yield repr(str(v))
    except UnicodeEncodeError:
      yield repr(v)
  elif isinstance(v, long):  # Take out the L when unnecessary
    yield repr(int(v))
  else:
    yield repr(v)


def list_pretty_iterator(pretty_iter):
  l = []
  from types import GeneratorType
  for pretty_val in pretty_iter:
    if isinstance(pretty_val, GeneratorType):
      for iter_pretty_val in pretty_val:
        l += list_pretty_iterator(iter_pretty_val)
    else:
      l.append(pretty_val)
  return l


def prettify(data, indent=4, nest_level=0):
  return list_pretty_iterator(_pretty_merge_value(data, indent=indent, nest_level=nest_level))
