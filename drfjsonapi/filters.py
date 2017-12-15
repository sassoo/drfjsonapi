"""
    drfjsonapi.filters
    ~~~~~~~~~~~~~~~~~~~

    DRF relationship fields to assist with a JSON API spec
    compliant API.
"""

from rest_framework.filters import BaseFilterBackend, OrderingFilter
from .exceptions import InvalidFilterParam, InvalidIncludeParam, InvalidSortParam


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
        except AttributeError:
            filterset = None

        if not filterset and 'filter' in request.query_params.keys():
            raise InvalidFilterParam('"filter" query parameters are not supported')

        filters = ()

        if filterset:
            filters = filterset.to_internal_value(request)
            filters = filterset.validate(filters)
            queryset = filterset.filter_queryset(queryset, filters)

        request.jsonapi_filter = filters
        return queryset


class IncludeFilter(JsonApiFilter, BaseFilterBackend):
    """ Support the inclusion of compound documents

    The `filter_queryset` entry point method requires the view provided
    to have an `includeset_class` attribute or IncludeSet instance
    returned from the views `get_includeset()`.

    The santizied includes query params will be available on the
    request object via a `jsonapi_include` attribute.
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


class SortFilter(JsonApiFilter, OrderingFilter):
    """ Override default OrderingFilter to be JSON API compliant

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
