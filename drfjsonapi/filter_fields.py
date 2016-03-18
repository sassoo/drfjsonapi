"""
    drfjsonapi.filter_fields
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    DRF filter fields to assist with a JSONAPI spec compliant
    API implementing resource filter query parameters.

    The `FilterField` object & other objects that may subclass it
    leverages existing DRF serializers & the fields defined for
    existing resources. It gains all of the validation & casting
    capabilities of DRF serializer fields without needing a bunch
    of 3rd party stuff that uses forms for validations.
"""

from django.core.exceptions import ImproperlyConfigured
from rest_framework import serializers
from rest_framework.exceptions import ValidationError


class FilterField(object):
    """ Base FilterField object used for declaring serializer filters

    A `FilterField` takes a DRF native serializer field
    instance, with optional validations, & a list of acceptable
    lookup operators.

    A lookup operator & value can be passed into the `validate`
    method to ensure only the explicit filtering operators are
    available.
    """

    drf_field = None
    lookups = ()

    def __init__(self, **kwargs):

        self.field = kwargs.get('field', self.drf_field)
        self.lookups = kwargs.get('lookups', self.lookups)

    def validate(self, lookup, value):
        """ Run the fields natve `run_validation` method

        If no exceptions are raised then return whatever the
        native `run_validation` method would return which is
        typically a coerced version of the value.
        """

        if not self.field:
            msg = '"%s" requires a valid DRF serializer field to ' \
                  'perform proper validations' % self.__class__.__name__
            raise ImproperlyConfigured(msg)
        elif lookup not in self.lookups:
            msg = 'Unsupported lookup operator of "%s"' % lookup
            raise ValidationError(msg)
        else:
            return self.field.run_validation(data=value)


class BooleanFilterField(FilterField):
    """ General BooleanField filter with common bool lookups """

    drf_field = serializers.BooleanField()
    lookups = ('exact',)


class CharFilterField(FilterField):
    """ General CharField filter with common string lookups """

    drf_field = serializers.CharField(max_length=300)
    lookups = ('contains', 'icontains', 'endswith', 'iendswith',
               'exact', 'iexact', 'startswith', 'istartswith')


class DateTimeFilterField(FilterField):
    """ General DateTimeField filter with common datetime lookups """

    drf_field = serializers.DateTimeField()
    lookups = ('exact', 'gt', 'gte', 'lt', 'lte')


class IntegerFilterField(FilterField):
    """ General IntegerField filter with common numeric lookups """

    drf_field = serializers.IntegerField()
    lookups = ('contains', 'endswith', 'exact', 'gt', 'gte',
               'lt', 'lte', 'startswith')


class RelatedFilterField(object):
    """ Used for filters referencing a relationship field """

    def validate(self, *args, **kwargs):
        """ Ignore on RelatedFiltFields

        The validation will be performed on the relationships
        ultimate field. This is just a hop along the path.
        """
        pass
