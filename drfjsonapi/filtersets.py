"""
    drfjsonapi.filtersets
    ~~~~~~~~~~~~~~~~~~~~~

    Interface for handling the JSON API filter query parameters.
"""

import re

from django.db.models import Q
from rest_framework.exceptions import ValidationError
from .exceptions import InvalidFilterParam


class JsonApiFilterSet:
    """ This should be subclassed by custom FilterSets """

    fields = {}
    max_params = 15

    def __init__(self, context=None):
        """ Context will include the request & view """

        self.context = context or {}

    def filter_queryset(self, queryset, filters):
        """ Turn the vetted query param filters into Q object expressions """

        q_filter = Q()
        for param, value in filters.items():
            q_filter.add(Q((param, value)), Q.AND)
        return queryset.filter(q_filter).distinct()

    def to_internal_value(self, request):
        """ Coerce & validate the query params & values

        Loop through all the query parameters & use a regular
        expression to find all the filters that match a format
        of:

            filter[<field>__<lookup>]=<value>

        An example filter of `filter[home__city__exact]=Orlando`
        would return a dict of:

            {'home__city__exact': 'Orlando'}

        """

        filters = {}
        regex = re.compile(r'^filter\[([A-Za-z0-9_.]+)\]$')
        for param, value in request.query_params.items():
            try:
                param = regex.match(param).groups()[0]
                filters[param] = value
            except (AttributeError, IndexError):
                continue
        return filters

    def validate(self, filters):
        """ Hook to validate the coerced data """

        if len(filters) > self.max_params:
            msg = 'The request has "%s" filter query parameters which ' \
                  'exceeds the max number of "%s" that can be requested.' \
                  % (len(filters), self.max_params)
            raise InvalidFilterParam(msg)

        return {k: self.validate_filter(k, v) for k, v in filters.items()}

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
