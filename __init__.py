import copy
import hashlib
import logging
import os
import pickle
from google.appengine.api import users
from google.appengine.ext import db


def DerivedProperty(func=None, *args, **kwargs):
  """Implements a 'derived' datastore property.

  Derived properties are not set directly, but are instead generated by a
  function when required. They are useful to provide fields in the datastore
  that can be used for filtering or sorting in ways that are not otherwise
  possible with unmodified data - for example, filtering by the length of a
  BlobProperty, or case insensitive matching by querying the lower cased version
  of a string.

  DerivedProperty can be declared as a regular property, passing a function as
  the first argument, or it can be used as a decorator for the function that
  does the calculation, either with or without arguments.

  Example:

  >>> class DatastoreFile(db.Model):
  ...   name = db.StringProperty(required=True)
  ...   name_lower = DerivedProperty(lambda self: self.name.lower())
  ...
  ...   data = db.BlobProperty(required=True)
  ...   @DerivedProperty
  ...   def size(self):
  ...     return len(self.data)
  ...
  ...   @DerivedProperty(name='sha1')
  ...   def hash(self):
  ...     return hashlib.sha1(self.data).hexdigest()

  You can read derived properties the same way you would regular ones:

  >>> file = DatastoreFile(name='Test.txt', data='Hello, world!')
  >>> file.name_lower
  'test.txt'
  >>> file.hash
  '943a702d06f34599aee1f8da8ef9f7296031d699'

  Attempting to set a derived property will throw an error:

  >>> file.name_lower = 'foobar'
  Traceback (most recent call last):
      ...
  DerivedPropertyError: Cannot assign to a DerivedProperty

  When persisted, derived properties are stored to the datastore, and can be
  filtered on and sorted by:

  >>> file.put() # doctest: +ELLIPSIS
  datastore_types.Key.from_path(u'DatastoreFile', ...)

  >>> DatastoreFile.all().filter('size =', 13).get().name
  u'Test.txt'
  """
  if func:
    # Regular invocation, or used as a decorator without arguments
    return _DerivedProperty(func, *args, **kwargs)
  else:
    # We're being called as a decorator with arguments
    def decorate(decorated_func):
      return _DerivedProperty(decorated_func, *args, **kwargs)
    return decorate


class _DerivedProperty(db.Property):
  def __init__(self, derive_func, *args, **kwargs):
    """Constructor.

    Args:
      func: A function that takes one argument, the model instance, and
        returns a calculated value.
    """
    super(_DerivedProperty, self).__init__(*args, **kwargs)
    self.derive_func = derive_func

  def __get__(self, model_instance, model_class):
    if model_instance is None:
      return self
    return self.derive_func(model_instance)

  def __set__(self, model_instance, value):
    raise db.DerivedPropertyError("Cannot assign to a DerivedProperty")


class LowerCaseProperty(_DerivedProperty):
  """A convenience class for generating lower-cased fields for filtering.

  Example usage:

  >>> class Pet(db.Model):
  ...   name = db.StringProperty(required=True)
  ...   name_lower = LowerCaseProperty(name)

  >>> pet = Pet(name='Fido')
  >>> pet.name_lower
  'fido'
  """
  def __init__(self, property, *args, **kwargs):
    """Constructor.

    Args:
      property: The property to lower-case.
    """
    super(LowerCaseProperty, self).__init__(
        lambda self: property.__get__(self, type(self)).lower(),
        *args, **kwargs)


class LengthProperty(_DerivedProperty):
  """A convenience class for recording the length of another field

  Example usage:

  >>> class TagList(db.Model):
  ...   tags = db.ListProperty(unicode, required=True)
  ...   num_tags = LengthProperty(tags)

  >>> tags = TagList(tags=[u'cool', u'zany'])
  >>> tags.num_tags
  2
  """
  def __init__(self, property, *args, **kwargs):
    """Constructor.

    Args:
      property: The property to lower-case.
    """
    super(LengthProperty, self).__init__(
        lambda self: len(property.__get__(self, type(self))),
        *args, **kwargs)


def TransformProperty(source, transform_func=None, *args, **kwargs):
  """Implements a 'transform' datastore property.

  TransformProperties are similar to DerivedProperties, but with two main
  differences:
  - Instead of acting on the whole model, the transform function is passed the
    current value of a single property which was specified in the constructor.
  - Property values are calculated when the property being derived from is set,
    not when the TransformProperty is fetched. This is more efficient for
    properties that have significant expense to calculate.

  TransformProperty can be declared as a regular property, passing the property
  to operate on and a function as the first arguments, or it can be used as a
  decorator for the function that does the calculation, with the property to
  operate on passed as an argument.

  Example:

  >>> class DatastoreFile(db.Model):
  ...   name = db.StringProperty(required=True)
  ...
  ...   data = db.BlobProperty(required=True)
  ...   size = TransformProperty(data, len)
  ...
  ...   @TransformProperty(data)
  ...   def hash(val):
  ...     return hashlib.sha1(val).hexdigest()

  You can read transform properties the same way you would regular ones:

  >>> file = DatastoreFile(name='Test.txt', data='Hello, world!')
  >>> file.size
  13
  >>> file.data
  'Hello, world!'
  >>> file.hash
  '943a702d06f34599aee1f8da8ef9f7296031d699'

  Updating the property being transformed automatically updates any
  TransformProperties depending on it:

  >>> file.data = 'Fubar'
  >>> file.data
  'Fubar'
  >>> file.size
  5
  >>> file.hash
  'df5fc9389a7567ddae2dd29267421c05049a6d31'

  Attempting to set a transform property directly will throw an error:

  >>> file.size = 123
  Traceback (most recent call last):
      ...
  DerivedPropertyError: Cannot assign to a TransformProperty

  When persisted, transform properties are stored to the datastore, and can be
  filtered on and sorted by:

  >>> file.put() # doctest: +ELLIPSIS
  datastore_types.Key.from_path(u'DatastoreFile', ...)

  >>> DatastoreFile.all().filter('size =', 13).get().hash
  '943a702d06f34599aee1f8da8ef9f7296031d699'
  """
  if transform_func:
    # Regular invocation
    return _TransformProperty(source, transform_func, *args, **kwargs)
  else:
    # We're being called as a decorator with arguments
    def decorate(decorated_func):
      return _TransformProperty(source, decorated_func, *args, **kwargs)
    return decorate


class _TransformProperty(db.Property):
  def __init__(self, source, transform_func, *args, **kwargs):
    """Constructor.

    Args:
      source: The property the transformation acts on.
      transform_func: A function that takes the value of source and transforms
        it in some way.
    """
    super(_TransformProperty, self).__init__(*args, **kwargs)
    self.source = source
    self.transform_func = transform_func

  def __orig_attr_name(self):
    return '_ORIGINAL' + self._attr_name()

  def __transformed_attr_name(self):
    return self._attr_name()

  def __get__(self, model_instance, model_class):
    if model_instance is None:
      return self
    last_val = getattr(model_instance, self.__orig_attr_name(), None)
    current_val = self.source.__get__(model_instance, model_class)
    if last_val == current_val:
      return getattr(model_instance, self.__transformed_attr_name())
    transformed_val = self.transform_func(current_val)
    setattr(model_instance, self.__orig_attr_name(), current_val)
    setattr(model_instance, self.__transformed_attr_name(), transformed_val)
    return transformed_val

  def __set__(self, model_instance, value):
    raise db.DerivedPropertyError("Cannot assign to a TransformProperty")


class KeyProperty(db.Property):
  """A property that stores a key, without automatically dereferencing it.

  Example usage:

  >>> class SampleModel(db.Model):
  ...   sample_key = KeyProperty()

  >>> model = SampleModel()
  >>> model.sample_key = db.Key.from_path("Foo", "bar")
  >>> model.put() # doctest: +ELLIPSIS
  datastore_types.Key.from_path(u'SampleModel', ...)

  >>> model.sample_key # doctest: +ELLIPSIS
  datastore_types.Key.from_path(u'Foo', u'bar', ...)
  """
  def validate(self, value):
    """Validate the value.

    Args:
      value: The value to validate.
    Returns:
      A valid key.
    """
    if isinstance(value, basestring):
      value = db.Key(value)
    if value is not None:
      if not isinstance(value, db.Key):
        raise TypeError("Property %s must be an instance of db.Key"
                        % (self.name,))
    return super(KeyProperty, self).validate(value)


class PickleProperty(db.Property):
  """A property for storing complex objects in the datastore in pickled form.

  Example usage:

  >>> class PickleModel(db.Model):
  ...   data = PickleProperty()

  >>> model = PickleModel()
  >>> model.data = {"foo": "bar"}
  >>> model.data
  {'foo': 'bar'}
  >>> model.put() # doctest: +ELLIPSIS
  datastore_types.Key.from_path(u'PickleModel', ...)

  >>> model2 = PickleModel.all().get()
  >>> model2.data
  {'foo': 'bar'}
  """

  data_type = db.Blob

  def get_value_for_datastore(self, model_instance):
    value = self.__get__(model_instance, model_instance.__class__)
    if value is not None:
      return db.Blob(pickle.dumps(value))

  def make_value_from_datastore(self, value):
    if value is not None:
      return pickle.loads(str(value))

  def default_value(self):
    """If possible, copy the value passed in the default= keyword argument.
    This prevents mutable objects such as dictionaries from being shared across
    instances."""
    return copy.copy(self.default)

class SetProperty(db.ListProperty):
  """A property that stores a set of things.

  This is a parameterized property; the parameter must be a valid
  non-list data type, and all items must conform to this type.

  Example usage:

  >>> class SetModel(db.Model):
  ...   a_set = SetProperty(int)

  >>> model = SetModel()
  >>> model.a_set = set([1, 2, 3])
  >>> model.a_set
  set([1, 2, 3])
  >>> model.a_set.add(4)
  >>> model.a_set
  set([1, 2, 3, 4])
  >>> model.put() # doctest: +ELLIPSIS
  datastore_types.Key.from_path(u'SetModel', ...)

  >>> model2 = SetModel.all().get()
  >>> model2.a_set
  set([1L, 2L, 3L, 4L])
  """

  def validate(self, value):
    value = db.Property.validate(self, value)
    if value is not None:
      if not isinstance(value, (set, frozenset)):
        raise db.BadValueError('Property %s must be a set' % self.name)

      value = self.validate_list_contents(value)
    return value

  def default_value(self):
    return set(db.Property.default_value(self))

  def get_value_for_datastore(self, model_instance):
    return list(super(SetProperty, self).get_value_for_datastore(model_instance))

  def make_value_from_datastore(self, value):
    if value is not None:
      return set(super(SetProperty, self).make_value_from_datastore(value))

  def get_form_field(self, **kwargs):
    from django import newforms as forms
    defaults = {'widget': forms.Textarea,
                'initial': ''}
    defaults.update(kwargs)
    return super(SetProperty, self).get_form_field(**defaults)

  def get_value_for_form(self, instance):
    value = super(SetProperty, self).get_value_for_form(instance)
    if not value:
      return None
    if isinstance(value, set):
      value = '\n'.join(value)
    return value

  def make_value_from_form(self, value):
    if not value:
      return []
    if isinstance(value, basestring):
      value = value.splitlines()
    return set(value)


class InvalidDomainError(Exception):
  """Raised when something attempts to access data belonging to another domain."""


class CurrentDomainProperty(db.Property):
  """A property that restricts access to the current domain.
  
  Example usage:
  
  >>> class DomainModel(db.Model):
  ...   domain = CurrentDomainProperty()
  
  >>> os.environ['HTTP_HOST'] = 'domain1'
  >>> model = DomainModel()
  
  The domain is set automatically:
  
  >>> model.domain
  u'domain1'
  
  You cannot change the domain:
  
  >>> model.domain = 'domain2'  # doctest: +ELLIPSIS
  Traceback (most recent call last):
      ...
  InvalidDomainError: Domain 'domain1' attempting to illegally access data for domain 'domain2'
  
  >>> key = model.put()
  >>> model = DomainModel.get(key)
  >>> model.domain
  u'domain1'
  
  You cannot write the data from another domain:
  
  >>> os.environ['HTTP_HOST'] = 'domain2'
  >>> model.put() # doctest: +ELLIPSIS
  Traceback (most recent call last):
      ...
  InvalidDomainError: Domain 'domain2' attempting to allegally modify data for domain 'domain1'
  
  Nor can you read it:
  
  >>> DomainModel.get(key)  # doctest: +ELLIPSIS
  Traceback (most recent call last):
      ...
  InvalidDomainError: Domain 'domain2' attempting to illegally access data for domain 'domain1'
  
  Admin users can read and write data for other domains:
  
  >>> os.environ['USER_IS_ADMIN'] = '1'
  >>> model = DomainModel.get(key)
  >>> model.put()  # doctest: +ELLIPSIS
  datastore_types.Key.from_path(u'DomainModel', ...)
  
  You can also define models that should permit read or write access from
  other domains:
  
  >>> os.environ['USER_IS_ADMIN'] = '0'
  >>> class DomainModel2(db.Model):
  ...   domain = CurrentDomainProperty(allow_read=True, allow_write=True)
  
  >>> model = DomainModel2()
  >>> model.domain
  u'domain2'
  >>> key = model.put()
  
  >>> os.environ['HTTP_HOST'] = 'domain3'
  >>> model = DomainModel2.get(key)
  >>> model.put()  # doctest: +ELLIPSIS
  datastore_types.Key.from_path(u'DomainModel2', ...)
  """

  def __init__(self, allow_read=False, allow_write=False, *args, **kwargs):
    """Constructor.
    
    Args:
      allow_read: If True, allow entities with this property to be read, but not
        written, from other domains.
      allow_write: If True, allow entities with this property to be modified
        from other domains.
    """
    self.allow_read = allow_read
    self.allow_write = allow_write
    super(CurrentDomainProperty, self).__init__(*args, **kwargs)

  def __set__(self, model_instance, value):
    if not value:
      value = unicode(os.environ['HTTP_HOST'])
    elif (value != os.environ['HTTP_HOST'] and not self.allow_read
          and not users.is_current_user_admin()):
      raise InvalidDomainError(
          "Domain '%s' attempting to illegally access data for domain '%s'"
          % (os.environ['HTTP_HOST'], value))
    super(CurrentDomainProperty, self).__set__(model_instance, value)

  def get_value_for_datastore(self, model_instance):
    value = super(CurrentDomainProperty, self).get_value_for_datastore(
        model_instance)
    if (value != os.environ['HTTP_HOST'] and not users.is_current_user_admin()
        and not self.allow_write):
      raise InvalidDomainError(
          "Domain '%s' attempting to allegally modify data for domain '%s'"
          % (os.environ['HTTP_HOST'], value))
    return value


class ChoiceProperty(db.IntegerProperty):
  """A property for efficiently storing choices made from a finite set.

  This works by mapping each choice to an integer.  The choices must be hashable
  (so that they can be efficiently mapped back to their corresponding index).

  Example usage:

  >>> ColorChoiceProp = make_choice_property('ColorChoiceProp', ['red', 'green', 'blue'])
  >>> WeirdChoiceProp = make_choice_property('WeirdChoiceProp', {None:0, 'alpha':1,'beta':4})
  >>> class ChoiceModel(db.Model):
        a_choice = ColorChoiceProp()
        b_choice = WeirdChoiceProp()

  >>> model = ChoiceModel(a_choice='green')
  >>> model.a_choice
  'green'
  >>> model.b_choice
  None
  >>> model.b_choice = 'beta'
  >>> model.b_choice
  'beta'
  >>> model.put() # doctest: +ELLIPSIS
  datastore_types.Key.from_path(u'ChoiceModel', ...)

  >>> model2 = ChoiceModel.all().get()
  >>> model2.a_choice
  'green'
  >>> model.b_choice
  'beta'
  >>> ChoiceModel.gql("WHERE a_choice = :1", ColorChoiceProp.c2i('green')).count()
  1
  """
  @classmethod
  def get_choices(cls):
    return cls.CHOICE_TO_INDEX.keys()

  @classmethod
  def c2i(cls, choice):
    """Converts a choice to its datastore representation."""
    return cls.CHOICE_TO_INDEX[choice]

  def __get__(self, model_instance, model_class):
    index = super(ChoiceProperty, self).__get__(model_instance, model_class)
    return self.INDEX_TO_CHOICE[index]

  def __set__(self, model_instance, value):
    try:
      index = self.c2i(value)
    except KeyError:
      raise db.BadValueError('Property %s must be one of the allowed choices: %s' %
                          (self.name, self.get_choices()))
    super(ChoiceProperty, self).__set__(model_instance, index)

  def get_value_for_datastore(self, model_instance):
    # just use the underlying value from the parent
    return super(ChoiceProperty, self).__get__(model_instance, model_instance.__class__)

  def make_value_from_datastore(self, value):
    if value is None:
      return None
    return self.INDEX_TO_CHOICE[value]

def make_choice_property(cls_name, choices=None):
  """Create a new ChoiceProperty.

  If a list of choices is passed, then each element will be encoded as the index
  at which it appears.

  If a dictionary of choices is passed, then it must map choices to their
  corresponding unique int value.  This method must be used if choices should
  not be encoded as 0 to N-1 (as with the list of choices).
  """
  if isinstance(choices, list):
    i2c = choices
    c2i = dict((c,i) for i,c in enumerate(choices))
  elif isinstance(choices, dict):
    for v in choices.itervalues():
      if not isinstance(v, int):
        raise TypeError, 'choice dictionary values must be ints: got %s' % (v,)
    i2c = dict((v,k) for k,v in choices.iteritems())
    c2i = choices
  else:
    raise TypeError, 'choices must be a list or a dictionary'

  new_class_vars = dict(INDEX_TO_CHOICE=i2c,
                        CHOICE_TO_INDEX=c2i,
                        data_type=type(i2c[0]))
  return type(cls_name, (ChoiceProperty,), new_class_vars)
