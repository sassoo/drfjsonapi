"""
    drfjsonapi.filters
    ~~~~~~~~~~~~~~~~~~~

    DRF relationship fields to assist with a JSON API spec
    compliant API.
"""

import itertools
import re

from collections import OrderedDict
from django.core.exceptions import ImproperlyConfigured
from django.db.models.query import Prefetch
from rest_framework.filters import (
    BaseFilterBackend,
    OrderingFilter as _OrderingFilter,
)
from .exceptions import InvalidIncludeParam, InvalidSortParam
from .utils import _dict_merge, _reduce_str_to_dict


__all__ = ('FieldFilter', 'IncludeFilter', 'OrderingFilter')


class JsonApiFilter(object):
    """ For easy `isinstance` checks """
    pass


class FieldFilter(JsonApiFilter, BaseFilterBackend):
    """ Support the filtering of arbitrary resource fields

    The `filter_queryset` entry point method requires the view
    provided to have a `get_filterset` method which is already
    present on DRF GenericAPIView instances & it MUST return a
    filterset for the primary data.

    That filterset will be used to validate the `filter` query
    param values.

    All vetted filters will have filter logic attached to the
    primary datasets queryset.
    """

    def filter_queryset(self, request, queryset, view):
        """ DRF entry point into the custom FilterBackend """

        try:
            filterset = view.get_filterset()
            if not filterset:
                raise AttributeError
        except AttributeError:
            msg = 'Using "%s" requires a view that returns a ' \
                  'filterset from "get_filterset()"'
            raise ImproperlyConfigured(msg % self.__class__.__name__)

        filters = self.get_query_filters(request)
        if filters:
            filters = filterset.to_internal_value(filters)
            filters = filterset.validate(filters)
            q_filter = filterset.get_filter_expressions(filters)
            queryset = queryset.filter(q_filter).distinct()
        return queryset

    def get_query_filters(self, request):
        """ Return the sanitized `filter` query parameters

        Loop through all the query parameters & use a regular
        expression to find all the filters that match a format
        of:

            filter[<field>__<lookup>]=<value>

        A dict will be generated for each match where the key
        is the filter expression & the value is the value as
        is in the query.

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
    """ Support the include of compound documents

    The `filter_queryset` entry point method requires the view
    provided to have a `get_serializer` method & that MUST return
    a serializer instance.

    That serializer will be used to validate the `include` query
    param values. If the global `max_includes` property limit
    is not exceeded then each include is tested for eligibility.

    For an include to be eligible it MUST meet all of the
    following criteria:

        1. Not exceed the `max_relations` limit of nested
           includes. For example, '?include=foo.bar.baz'
           would be 3 relations.

        2. Be listed in the serializers `get_includables`
           or `get_default_includables` methods

        3. Return a serializer when calling the serializers
           `get_related_serializer` method.

    Each individual relation in an include will be validated
    according to steps 2-3. An include of 'actor.movies' for
    instance would have both 'actor' & 'movies' vetted against
    steps 2-3 by walking the chain of related serializers.

    All vetted includes will then have prefetching logic attached
    to the primary datasets queryset for efficiency. You can also
    override the default Prefetch's queryset by returning one
    from the serializers `get_related_queryset` method.

    Finally, if no includes are provided in the query param
    then any fields returned from the `get_default_includables`
    method on the serializer will be automatically prefeteched &
    included.
    """

    max_includes = 25
    max_relations = 3

    def __init__(self):
        """ The superclass doesn't have an __init__ defined """

        self._cache = OrderedDict()

    def filter_queryset(self, request, queryset, view):
        """ DRF entry point into the custom FilterBackend """

        try:
            serializer = view.get_serializer()
            if not serializer:
                raise AttributeError
        except AttributeError:
            msg = 'Using "%s" requires a view that returns a ' \
                  'serializer from "get_serializer()"'
            raise ImproperlyConfigured(msg % self.__class__.__name__)

        includes = self.get_query_includes(request)
        if includes:
            self.validate_includes(includes, serializer)
        else:
            self.process_default_includes(serializer)

        queryset = queryset.prefetch_related(*self.get_prefetches())
        request._includes = self._get_cache()
        return queryset

    def _get_cache(self):
        """ Generate a cache for later processing by the renderer """

        cache = {}
        for key, val in self._cache.items():
            _dict = _reduce_str_to_dict(key, val)
            _dict_merge(cache, _dict)
        return cache

    def _update_cache(self, field, serializer, path=None):
        """ Add an entry to the include_cache

        Order is important with django & that's why an
        OrderedDict is used. This will call the fields
        `get_related_queryset` method for extra filtering.
        """

        path = path or field
        queryset = serializer.get_related_queryset(field)
        self._cache[path] = {
            'prefetch': Prefetch(path, queryset=queryset),
            'serializer': serializer.get_related_serializer(field),
        }

    def get_prefetches(self):
        """ Return the list of generated Prefetch objects """

        return [value.pop('prefetch') for value in self._cache.values()]

    def get_query_includes(self, request):
        """ Return the sanitized `include` query parameters

        Handles comma separated & multiple include params &
        returns a tuple of duplicate free strings
        """

        includes = request.query_params.getlist('include')
        includes = [include.split(',') for include in includes]
        includes = list(itertools.chain(*includes))
        return tuple(set(includes))

    def process_default_includes(self, serializer):
        """ Include all of the default fields

        This should look for related fields with default
        includes BUT only if none were specified through
        an include query parameter per the JSON API spec.
        """

        for field in serializer.get_default_includables():
            self._update_cache(field, serializer)

    def validate_includes(self, includes, serializer):
        """ Validate all the sanitized includeed query parameters """

        if len(includes) > self.max_includes:
            msg = 'The include query parameter requested "%s" additional ' \
                  'compound documents exceeding the max number of "%s"' \
                  % (len(includes), self.max_includes)
            raise InvalidIncludeParam(msg)

        for include in includes:
            self.validate_include(include, serializer)

    def validate_include(self, include, serializer):
        """ Validate each included query param individually

        Walk the serializers for deeply nested include requests
        to ensure they are allowed to be includeed.
        """

        relations = include.split('.')
        if len(relations) > self.max_relations:
            msg = 'The "%s" include query parameter exceeds the max' \
                  'relations limit of "%s"' % (include, self.max_relations)
            raise InvalidIncludeParam(msg)

        for idx, relation in enumerate(relations):
            related_path = '__'.join(relations[:idx + 1])

            if not serializer or relation not in serializer.get_includables():
                msg = 'The "%s" include query parameter requested is ' \
                      'either an invalid field or not allowed to be ' \
                      'included' % include
                raise InvalidIncludeParam(msg)

            self._update_cache(relation, serializer, related_path)
            serializer = serializer.get_related_serializer(relation)


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
