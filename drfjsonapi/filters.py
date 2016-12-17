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
from rest_framework.exceptions import ValidationError
from rest_framework.filters import (
    BaseFilterBackend,
    OrderingFilter as _OrderingFilter,
)
from .exceptions import (
    InvalidFilterParam,
    InvalidIncludeParam,
    InvalidSortParam,
)
from .filter_fields import RelatedFilterField
from .utils import _dict_merge, _reduce_str_to_dict


__all__ = ('FieldFilter', 'IncludeFilter', 'OrderingFilter', 'SparseFilter')


class JsonApiFilter(object):
    """ For easy `isinstance` checks """
    pass


class FieldFilter(JsonApiFilter, BaseFilterBackend):
    """ Support the filtering of arbitrary resource fields

    JSON API details
    ~~~~~~~~~~~~~~~~

    This filter can be used to support the `filter` query param
    for requesting arbitrary filtering strategies related to the
    primary data requested according to the JSON API spec.

    Per JSON API spec, it's agnostic about how filtering is done
    but it does outline some examples which are adopted. Namely,
    the filter query param brackets the field, optionally, with
    dot notation relationships.

    Implementation details
    ~~~~~~~~~~~~~~~~~~~~~~

    The `filter_queryset` entry point method requires the view
    provided to have a `get_serializer` method which is already
    present on DRF GenericAPIView instances & it MUST return a
    serializer for the primary data.

    That serializer will be used to validate the `filter` query
    param values. If the global `max_filters` property limit is
    not exceeded then each filter is tested for eligibility.

    For a field to be eligible for it MUST meet all of the
    following criteria:

        1. Not exceed the `max_relations` limit of nested
           filters. For example, '?filter[foo__bar__baz]=hi'
           would be 3 relations.

        2. Exist as a key in the `get_filterable_fields` dict
           when called on the serializer

        3. Related fields must use the RelatedFilterField.
           Also, related fields must return a serializer from
           the fields `get_serializer` method (not the filter
           field but the serializers field)

        4. Contain a valid lookup operator in the FilterFields
           `lookups` attribute list.

        5. Pass all validations on the FilerField

    All vetted filters will have filter logic attached to the
    primary datasets queryset. You can also define an additional
    mandatory default queryset for each FilterField object by
    returning one from the serializer fields `get_filtered_queryset`
    method.
    """

    max_filters = 10
    max_relations = 3

    def __init__(self):
        """ The superclass doesn't have an __init__ defined """

        self._filters = {}

    def filter_queryset(self, request, queryset, view):
        """ DRF entry point into the custom FilterBackend """

        try:
            serializer = view.get_serializer()
            if not serializer:
                raise AttributeError
        except AttributeError:
            msg = 'Using "%s" requires a view that returns a serializer ' \
                  'from "get_serializer()"'
            raise ImproperlyConfigured(msg % self.__class__.__name__)

        filters = self.get_query_filters(request)
        if filters:
            self.validate_filters(filters, serializer)
            queryset = queryset.filter(**self.get_filters())
        return queryset

    def _update_filter(self, related_path, lookup, value):
        """ Generate & store an ORM based filter on the filter param """

        self._filters['%s__%s' % (related_path, lookup)] = value

    def _update_related_filter(self, related_path, field):
        """ Generate & store an ORM based filter on the filter param """

        queryset = field.get_filtered_queryset()
        if queryset is not None:
            self._filters['%s__in' % related_path] = queryset

    def get_filters(self):
        """ Return the list of generated Q filter objects """

        return self._filters

    def get_query_filters(self, request):
        """ Return the sanitized `filter` query parameters

        Loop through all the query parameters & use a regular
        expression to find all the filters that match a format
        of:

            filter[<field>__<lookup>]=<value>

        A tuple will be generated for each match containing the
        query parameter without the value (left of the = sign),
        the field to filter on (could be a relationship), the filter
        operator, and the value to filter with (right of the = sign).

        An example filter of `filter[home.city.exact]=Orlando`
        would return a tuple of:

            ('filter[home.city.exact]', 'home.city', 'exact', 'Orlando')

        :return:
            tuple of tuples
        """

        filters = []
        regex = re.compile(r'^filter\[([A-Za-z0-9_.]+)\]$')

        for param, value in request.query_params.items():
            match = regex.match(param)
            if match:
                field, _, lookup = match.groups()[0].rpartition('.')
                filters.append((param, field, lookup, value))
        return tuple(filters)

    def validate_filters(self, filters, serializer):
        """ Validate all the sanitized filter query parameters """

        if len(filters) > self.max_filters:
            msg = 'The request has "%s" filter query parameters which ' \
                  'exceeds the max number of "%s" that can be requested.' \
                  % (len(filters), self.max_filters)
            raise InvalidFilterParam(msg)

        for _filter in filters:
            self.validate_filter(_filter, serializer)

    def validate_filter(self, _filter, serializer):
        """ Validate each `filter` query param

        Walk the serializers for deeply nested (relations) filter
        requests to properly validate.
        """

        param, field, lookup, value = _filter
        relations = field.split('.')

        if len(relations) > self.max_relations:
            msg = 'The "%s" filter query parameter exceeds the max ' \
                  'relations limit of "%s"' % (param, self.max_relations)
            raise InvalidFilterParam(msg)

        for idx, relation in enumerate(relations):
            related_path = '__'.join(relations[:idx + 1])
            try:
                filter_field = serializer.get_filterable_fields()[relation]
                filter_field.validate(lookup, value)
            except (AttributeError, KeyError):
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

            if isinstance(filter_field, RelatedFilterField):
                field = serializer.fields[relation]
                self._update_related_filter(related_path, field)
                serializer = field.get_serializer()
            else:
                self._update_filter(related_path, lookup, value)


class IncludeFilter(JsonApiFilter, BaseFilterBackend):
    """ Support the include of compound documents

    JSON API details
    ~~~~~~~~~~~~~~~~

    This filter can be used to support the `include` query param
    for requesting additional compound documents related to the
    primary data requested according to the JSON API spec.

    This filter is JSON API compliant with the `include` query
    parameter in the following mentionable ways:

        1. The value of the include parameter MUST be a comma-separated
           (U+002C COMMA, ",") list of relationship paths.

        2. A relationship path is a dot-separated (U+002E FULL-STOP, ".")
           list of relationship names.

        3. If a server is unable to identify a relationship path
           or does not support include of resources from a path,
           it MUST respond with 400 Bad Request.

    In addition to the above guidelines, this filter will handle
    the scenario where multiple `include` query parameters are
    specified in the query string. It will collect all of them &
    uniquify them into a single tuple for validation checking.

    Implementation details
    ~~~~~~~~~~~~~~~~~~~~~~

    The `filter_queryset` entry point method requires the view
    provided to have a `get_serializer` method which is already
    present on DRF GenericAPIView instances & it MUST return a
    serializer for the primary data.

    That serializer will be used to validate the `include` query
    param values. If the global `max_includes` property limit is
    not exceeded then each include is tested for eligibility.

    For an include to be eligible it MUST meet all of the
    following criteria:

        1. Not exceed the `max_relations` limit of nested
           includes. For example, '?include=foo.bar.baz'
           would be 3 relations.

        2. Be a readable field with the includable property
           set to True

        3. Return a serializer for the field from a call
           to the fields `get_serializer` method.

    Each individual relation in an include will be validated
    according to steps 2-3. An include of 'actor.movies' for
    instance would have both 'actor' & 'movies' vetted against
    steps 2-3 by walking the chain of related serializers.

    All vetted includes will then have prefetching logic attached
    to the primary datasets queryset for efficiency. You can also
    define a default queryset for each Prefetch object by returning
    one from the fields `get_filtered_queryset` method.

    Finally, if no includes are provided in the query param
    then any fields on the serializer with the `include` attr
    set to True will be automatically prefetech & included.
    """

    max_includes = 8
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
            msg = 'Using "%s" requires a view that returns a serializer ' \
                  'from "get_serializer()"'
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

    def _update_cache(self, path, field):
        """ Add an entry to the include_cache """

        self._cache[path] = {'field': field}

    def get_prefetches(self):
        """ Return the list of generated Prefetch objects

        Order is important with django & that's why an
        OrderedDict is used. This will call the fields
        `get_filtered_queryset` method for extra filtering.
        """

        prefetches = []
        for field, value in self._cache.items():
            queryset = value['field'].get_filtered_queryset()
            prefetches.append(Prefetch(field, queryset=queryset))
        return prefetches

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

        It will then auto include them. This is nice for
        related fields which should always be sideloaded
        where desired.
        """

        for name, field in serializer.get_includable_fields().items():
            if field.include:
                self._update_cache(name, field)

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
        """ Validate each includeed query param individually

        Walk the serializers for deeply nested include requests
        to ensure they are allowed to be includeed.
        """

        relations = include.split('.')
        if len(relations) > self.max_relations:
            msg = 'The "%s" include query parameter exceeds the max' \
                  'relations limit of "%s"' % (include, self.max_relations)
            raise InvalidIncludeParam(msg)

        for idx, relation in enumerate(relations):
            field = serializer.get_includable_fields().get(relation)
            related_path = '__'.join(relations[:idx + 1])

            if not field:
                msg = 'The "%s" include query parameter requested is ' \
                      'either an invalid field or not allowed to be ' \
                      'included' % include
                raise InvalidIncludeParam(msg)

            self._update_cache(related_path, field)
            serializer = field.get_serializer()


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

    def remove_invalid_fields(self, queryset, sorts, view):
        """ Override the default to support exception handling """

        allow = [item[0] for item in self.get_valid_fields(queryset, view)]
        order = []

        if len(sorts) > self.max_sorts:
            msg = 'Sorting on "%s" fields exceeds the max number of "%s"' \
                  % (len(sorts), self.max_sorts)
            raise InvalidSortParam(msg)

        for sort in sorts:
            if sort.lstrip('-') in allow:
                order.append(sort)
            elif self.relation_sep in sort:
                msg = 'The "%s" sort query parameter is not allowed ' \
                      'due to unpredictable results when sorting on ' \
                      'relationships' % sort
                raise InvalidSortParam(msg)
            else:
                msg = 'The "%s" sort query parameter either does not ' \
                      'exist or you are not allowed to sort on it' % sort
                raise InvalidSortParam(msg)

        return order


class SparseFilter(JsonApiFilter, BaseFilterBackend):
    """ Support the limiting of responses to only specific fields

    JSON API details
    ~~~~~~~~~~~~~~~~

    The JSON API spec reserves the `fields` query parameter for
    limiting fields that should be returned in the response.

    This filter can be used to support the `fields` query param
    for requesting only a subset of fields to be returned on a
    per resource type basis & is JSON API compliant in the
    following mentionable ways:

        1. The value of the fields parameter MUST be a
           comma-separated (U+002C COMMA, ",") list that
           refers to the name(s) of the fields to be returned.

        2. If a client requests a restricted set of fields for
           a given resource type, an endpoint MUST NOT include
           additional fields in resource objects of that type
           in its response.

    Implementation details
    ~~~~~~~~~~~~~~~~~~~~~~

    Currently, this doesn't do any validation or limiting of
    the django queryset. Instead, the pruning of fields is
    done by the serializer.

    We could eventually use something like `defer()` but
    this could cause performance issues if not done properly.
    """

    def filter_queryset(self, request, queryset, view):
        """ DRF entry point into the custom FilterBackend """

        sparse_fields = self.get_sparse_fields(request)
        request._sparse_cache = sparse_fields
        return queryset

    def get_sparse_fields(self, request):
        """ Return the sanitized `fields` query parameters

        Loop through all the query parameters & use a regular
        expression to find all the fields that match a format
        of:

            fields[<rtype>]=<value>

        A dict will be generated for each match containing the
        resource type in the fields query param as the key with
        a tuple value of fields to limit.

        An example fields of `fields[actors]=name,movies` would
        return a dict of:

            {'actors': ['name', 'movies', 'id', 'type']}

        The `id` & `type` members are always returned no matter
        the fields query param.
        """

        sparse_fields = {}
        regex = re.compile(r'^fields\[([A-Za-z0-9_]+)\]$')

        for param, val in request.query_params.items():
            match = regex.match(param)
            if match:
                vals = tuple(set(val.split(',') + ['id', 'type']))
                sparse_fields[match.groups()[0]] = vals
        return sparse_fields
