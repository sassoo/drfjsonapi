"""
    drfjsonapi.filtersets
    ~~~~~~~~~~~~~~~~~~~~~

    Interface for handling the JSON API filter query
    parameters.
"""

from django.db.models import Q
from rest_framework.exceptions import ValidationError
from .exceptions import InvalidFilterParam


class JsonApiFilterSet:
    """ This should be subclassed by custom FilterSets """

    filterable_fields = {}
    max_filters = 15

    def __init__(self, context=None):
        """ Context will include the request & view """

        self.context = context or {}

    def get_filter_expression(self, param, value):
        """ Return a valid django filter expression for the query param """

        return Q((param, value))

    def get_filter_expressions(self, data):
        """ Turn the vetted query param filters into Q object expressions """

        ret = Q()
        for param, value in data.items():
            ret.add(self.get_filter_expression(param, value), Q.AND)
        return ret

    def to_internal_value(self, data):
        """ Coerce & validate the query params & values """

        if len(data) > self.max_filters:
            msg = 'The request has "%s" filter query parameters which ' \
                  'exceeds the max number of "%s" that can be requested.' \
                  % (len(data), self.max_filters)
            raise InvalidFilterParam(msg)

        return {k: self.validate_filter(k, v) for k, v in data.items()}

    def validate(self, data):
        """ Hook to validate the coerced data """

        return data

    def validate_filter(self, param, value):
        """ Coerce & validate each query param & value one-by-one """

        # pylint: disable=invalid-name,unused-variable
        field, _, lookup = param.rpartition('__')

        try:
            validator = self.filterable_fields[field]
            return validator.validate(lookup, value)
        except KeyError:
            msg = 'The "%s" filter query parameter is invalid, the ' \
                  '"%s" field either does not exist on the requested ' \
                  'resource or you are not allowed to filter on it.' \
                  % (param, field)
            raise InvalidFilterParam(msg)
        except ValidationError as exc:
            msg = 'The "%s" filter query parameters value failed ' \
                  'validation checks with the following error(s): ' \
                  '%s' % (param, ' '.join(exc.detail))
            raise InvalidFilterParam(msg)
