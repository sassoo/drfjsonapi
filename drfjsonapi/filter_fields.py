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

import ast

from django.core.exceptions import ImproperlyConfigured
from rest_framework import serializers
from rest_framework.exceptions import ValidationError


class FilterField:
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

    def __init__(self, drf_field=None, lookups=None):

        self.field = drf_field or self.drf_field
        self.lookups = lookups or self.lookups

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


class DateFilterField(FilterField):
    """ General DateField filter with common date lookups """

    drf_field = serializers.DateField()
    lookups = ('exact', 'gt', 'gte', 'lt', 'lte')


class DateTimeFilterField(FilterField):
    """ General DateTimeField filter with common datetime lookups """

    drf_field = serializers.DateTimeField()
    lookups = ('exact', 'gt', 'gte', 'lt', 'lte')


class IntegerFilterField(FilterField):
    """ General IntegerField filter with common numeric lookups """

    drf_field = serializers.IntegerField()
    lookups = ('contains', 'endswith', 'exact', 'gt', 'gte',
               'lt', 'lte', 'startswith')


class IsNullFilterField(FilterField):
    """ Bool field supporting isnull lookups """

    drf_field = serializers.BooleanField()
    lookups = ('isnull',)


class ListFilterField(FilterField):
    """ General ListField filter with common list lookups """

    drf_field = serializers.ListField()
    lookups = ('contains',)

    def validate(self, lookup, value):
        """ FilterField override to ensure value is a list """

        try:
            value = ast.literal_eval(value)
        except:
            msg = '"%s" cannot be coerced into a list' % value
            raise ValidationError(msg)
        return super().validate(lookup, value)


class RelatedFilterField(FilterField):
    """ Used for filters referencing a relationship field """

    drf_field = serializers.BooleanField()
    lookups = ('isnull',)

    def validate(self, lookup, value):
        """ Ignore on RelatedFiltFields

        The validation will be performed on the relationships
        ultimate field if not in the lookups.
        """

        if lookup in self.lookups:
            return super().validate(lookup, value)
