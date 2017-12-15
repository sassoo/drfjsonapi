"""
    drfjsonapi.filters
    ~~~~~~~~~~~~~~~~~~~

    DRF relationship fields to assist with a JSON API spec
    compliant API.
"""

import re

from django.core.exceptions import ImproperlyConfigured
from rest_framework.filters import (
    BaseFilterBackend,
    OrderingFilter as _OrderingFilter,
)
from .exceptions import InvalidIncludeParam, InvalidSortParam


class JsonApiFilter(object):
    """ For easy `isinstance` checks """
    pass


class FieldFilter(JsonApiFilter, BaseFilterBackend):
    """ Support the filtering of arbitrary resource fields

    The `filter_queryset` entry point method requires the view
    provided to have a `get_filterset` method which is already
    present on DRF GenericAPIView instances & it MUST return a
    JsonApiFilterset for the primary data.

    That filterset will be used to validate the `filter` query
    param values.
    """

    def filter_queryset(self, request, queryset, view):
        """ DRF entry point into the custom FilterBackend """

        try:
            filterset = view.get_filterset()
            if not filterset:
                raise AttributeError
        except AttributeError:
            msg = 'Using "%s" requires a view that returns a filterset ' \
                  'from "get_filterset()"' % self.__class__.__name__
            raise ImproperlyConfigured(msg)

        filters = self.parse(request)
        if filters:
            filters = filterset.to_internal_value(filters)
            filters = filterset.validate(filters)
            q_filter = filterset.get_filter_expressions(filters)
            queryset = queryset.filter(q_filter).distinct()
        return queryset

    def parse(self, request):
        """ Return the sanitized `filter` query parameters

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


class IncludeFilter(JsonApiFilter, BaseFilterBackend):
    """ Support the inclusion of compound documents

    The `filter_queryset` entry point method requires the view provided
    to have an `includeset_class` attribute or IncludeSet instance
    returned from the views `get_includeset()`.
    """

    def filter_queryset(self, request, queryset, view):
        """ DRF entry point into the custom FilterBackend """

        try:
            includeset = view.get_includeset()
        except AttributeError:
            includeset = None

        if not includeset and 'include' in request.query_params.keys():
            raise InvalidIncludeParam('"include" query parameters are not supported')

        include = ()

        if includeset:
            include = includeset.to_internal_value(request)
            include = includeset.validate(include)
            queryset = includeset.filter_queryset(queryset, include)

        request.jsonapi_include = include
        return queryset


class OrderingFilter(JsonApiFilter, _OrderingFilter):
    """ Override default OrderingFilter to be JSON API compliant

    JSON API details
    ~~~~~~~~~~~~~~~~

    The JSON API spec reserves the `sort` query parameter for
    ordering.

    This filter can be used to support the `sort` query param
    for requesting ordering preferences on the primary data &
    is JSON API compliant in the following mentionable ways:

        1. An endpoint MAY support multiple sort fields by
           allowing comma-separated (U+002C COMMA, ",") sort
           fields. Sort fields SHOULD be applied in the order
           specified.

        2. The sort order for each sort field MUST be ascending
           unless it is prefixed with a minus (U+002D HYPHEN-MINUS, "-"),
           in which case it MUST be descending.

    Implementation details
    ~~~~~~~~~~~~~~~~~~~~~~

    If the global `max_sorts` property limit is not exceeded then
    each sort is tested for eligibility.  To be eligible is MUST
    meet all of the following criteria:

        1. The sort cannot be a relationship sort. That is not
           supported currently & is generally frowned upon.

        2. Be present in the list of the DRF superclasses
           `get_valid_fields` method

    Step 2 is standard DRF OrderingFilter logic so read it's
    documentation for more info.
    """

    max_sorts = 3
    ordering_param = 'sort'
    relation_sep = '.'

    def remove_invalid_fields(self, queryset, fields, view, request):
        """ Override the default to support exception handling """

        if len(fields) > self.max_sorts:
            msg = 'Sorting on "%s" fields exceeds the maximum number of ' \
                  '"%s" sortable fields' % (len(fields), self.max_sorts)
            raise InvalidSortParam(msg)

        allow = [i[0] for i in self.get_valid_fields(queryset, view)]

        for field in fields:
            if not field.lstrip('-') in allow:
                msg = 'The "%s" sort query parameter either does not ' \
                      'exist or you are not allowed to sort on it' % field
                raise InvalidSortParam(msg)
            elif self.relation_sep in field:
                msg = 'The "%s" sort query parameter is not allowed due to ' \
                      'unpredictable results when sorting on relationships' % field
                raise InvalidSortParam(msg)

        return fields
