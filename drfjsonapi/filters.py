"""
    drfjsonapi.filters
    ~~~~~~~~~~~~~~~~~~~

    DRF relationship fields to assist with a JSON API spec
    compliant API.
"""

import itertools
import re

from .exceptions import (
    InvalidFilterParam,
    InvalidIncludeParam,
    InvalidSortParam,
    ManyExceptions,
)
from .filter_fields import RelatedFilterField
from .utils import _dict_merge, _reduce_str_to_dict
from collections import OrderedDict
from django.core.exceptions import ImproperlyConfigured
from django.db.models.query import Prefetch
from rest_framework.exceptions import ValidationError
from rest_framework.filters import (
    BaseFilterBackend,
    OrderingFilter as _OrderingFilter,
)


__all__ = ('FieldFilter', 'IncludeFilter', 'OrderingFilter', 'SparseFilter')


class FieldFilter(BaseFilterBackend):
    """ Support the filtering of arbitrary resource fields

    This filter can be used to support the `filter` query param
    for requesting arbitrary filtering strategies related to the
    primary data requested.

    The `filter_queryset` entry point method requires the view
    provided to have a `get_serializer` method which is already
    present on DRF GenericAPIView instances & it MUST return a
    serializer for the primary data.

    That serializer will be used to validate the `filter` query
    param values. For a field to be eligible for filtering it
    MUST meet all of the following criteria:

        1. Not exceed the `max_relations` limit of nested
           includes. For example, '?filter[foo__bar__baz]=hi'
           would be 3 relations.

        2. Exist in the keys() list of the `get_filter_fields`
           method of the serializer

        3. Related fields must use the RelatedFilterField class
           in the `get_filter_fields` values() list. Also, related
           fields must return a serializer for the field from a
           call to the serializers `get_related_serializer` method.

        4. Contain a valid lookup operator in the FilterFields
           `lookups` attribute list.

        5. Pass all validations on the FilerField

    All vetted filters will have filter logic attached to the
    primary datasets queryset. You can also define an additional
    mandatory default queryset for each FilterField object by
    returning one from the serializers `get_related_queryset` method.
    """

    max_filters = 10
    max_relations = 3
    relation_sep = '__'
    strict_mode = True

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

        filters = self.get_filter_params(request)
        if filters:
            self.validate_filters(filters, serializer)
            queryset = queryset.filter(**self.get_filters())
        return queryset

    def generate_filter(self, related_path, lookup, value):
        """ Generate & store an ORM based filter on the filter param """

        self._filters['%s__%s' % (related_path, lookup)] = value

    def generate_related_filter(self, related_path, field_name, serializer):
        """ Generate & store an ORM based filter on the filter param """

        queryset = serializer.get_related_queryset(field_name)
        if queryset is not None:
            self._filters['%s__in' % related_path] = queryset

    def get_filters(self):
        """ Return the list of generated Q filter objects """

        return self._filters

    def get_filter_params(self, request):
        """ Return the sanitized `filter` query parameters

        Loop through all the query parameters & use a regular
        expression to find all the filters that match a format
        of:

            filter[<field>__<lookup>]=<value>

        A tuple will be generated for each match containing the
        query parameter without the value (left of the = sign),
        the field to filter on (could be a relationship), the filter
        operator, and the value to filter with (right of the = sign).

        An example filter of `filter[home__city__exact]=Orlando`
        would return a tuple of:

            ('filter[home__city__exact]', 'home_city', 'exact', 'Orlando')

        :return:
            tuple of tuples
        """

        filters = []
        regex = re.compile(r'^filter\[([A-Za-z0-9_]+)\]$')

        for param, value in request.query_params.items():
            match = regex.match(param)
            if match:
                field, _, lookup = match.groups()[0].rpartition(
                    self.relation_sep
                )
                filters.append((param, field, lookup, value))
        return tuple(filters)

    def validate_filters(self, filters, serializer):
        """ Validate all the sanitized filter query parameters """

        excs = []

        if len(filters) > self.max_filters:
            msg = 'The request has "%s" filter query parameters which ' \
                  'exceeds the max number of "%s" that can be requested ' \
                  'in any one request' % (len(filters), self.max_filters)
            excs.append(InvalidFilterParam(msg))

        for _filter in filters:
            try:
                self.validate_filter(_filter, serializer)
            except InvalidFilterParam as exc:
                excs.append(exc)

        if self.strict_mode and excs:
            raise ManyExceptions(excs)

    def validate_filter(self, _filter, serializer):
        """ Validate each `filter` query param

        Walk the serializers for deeply nested (relations) filter
        requests to properly validate.
        """

        param, field, lookup, value = _filter
        relations = field.split(self.relation_sep)

        if len(relations) > self.max_relations:
            msg = 'The "%s" filter query parameter exceeds the max ' \
                  'relations limit of "%s"' % (param, self.max_relations)
            raise InvalidFilterParam(msg)

        for idx, relation in enumerate(relations):
            related_path = self.relation_sep.join(relations[:idx + 1])
            try:
                filter_field = serializer.get_filter_fields()[relation]
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
                self.generate_related_filter(related_path, relation,
                                             serializer)
                serializer = serializer.get_related_serializer(relation)
            else:
                self.generate_filter(related_path, lookup, value)


class IncludeFilter(BaseFilterBackend):
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

    In the case of guideline #3, a ManyException will be raised
    containing an InvalidIncludeParam exception for each include
    that fails validation checks. This allows the requestor to
    identify all of the errors in one round-turn.

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

        2. Exist in the list of the `get_include_field_names`
           method of the serializer

        3. Return a serializer for the field from a call to the
           serializers `get_related_serializer` method.

    The last step is needed to confirm a proper configuration
    since any includeed fields require there own serializer.

    Each individual relation in an include will be validated
    according to steps 2-3. An include of 'actor.movies' for
    instance would have both 'actor' & 'movies' vetted against
    steps 2-3 by walking the chain of related serializers.

    All vetted includes will then have prefetching logic attached
    to the primary datasets queryset for efficiency. You can also
    define a default queryset for each Prefetch object by returning
    one from the serializers `get_related_queryset` method.
    """

    max_includes = 8
    max_relations = 3
    relation_sep = '.'
    strict_mode = True

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



        prefetches = self.get_prefetches()
        queryset = queryset.prefetch_related(*prefetches)


        request._include_cache = self._get_cache()
        return queryset

    def _get_cache(self):
        """ Generate a cache for later processing by the renderer """

        cache = {}
        for key, val in self._cache.items():
            del val['queryset']
            val['serializer'] = val['serializer'].__class__

            _dict = _reduce_str_to_dict(key, val)
            _dict_merge(cache, _dict)
        return cache



    def _update_cache(self, path, field, serializer):

        self._cache[path] = {
            'field': field,
            'queryset': serializer.get_related_queryset(field),
            'serializer': serializer,
        }



    def get_prefetches(self):
        """ Return the list of generated Prefetch objects

        Order is important with django & that's why an OrderedDict
        is used.
        """

        prefetches = []
        for field, value in self._cache.items():
            prefetches.append(Prefetch(field, queryset=value['queryset']))
        return prefetches

    def get_query_includes(self, request):
        """ Return the sanitized `include` query parameters

        Handles comma separated & multiple include params & return
        a tuple of duplicate free strings
        """

        includes = request.query_params.getlist('include')
        includes = [include.split(',') for include in includes]
        includes = list(itertools.chain(*includes))
        return tuple(set(includes))



    def process_default_includes(self, serializer):
        """ XXX """

        # XXX this should look for related fields with
        # default includes if none specified & auto
        # include them
        #
        # If linkage=True and not RelatedField then
        # prefetch as well. No need on RelatedField
        # since it's optimized.
        #
        # If linkage=False and not included and not
        # RelatedField then prefetch to none. This
        # avoids an uneeded database hit. But how?
        # A queryset will always be needed.
        #
        # Use the `prefetch` kwarg on the related field
        # & if it's a callable run it with context
        # otherwise if it's a Prefetch instance use it.
        #
        # Call get_related_prefetch on the RelatedField
        # to get the filtered queryset if available


    def validate_includes(self, includes, serializer):
        """ Validate all the sanitized includeed query parameters """

        if len(includes) > self.max_includes:
            msg = 'The include query parameter requested "%s" additional ' \
                  'compound documents exceeding the max number of "%s"' \
                  % (len(includes), self.max_includes)
            raise InvalidIncludeParam(msg)

        excs = []
        for include in includes:
            try:
                self.validate_include(include, serializer)
            except InvalidIncludeParam as exc:
                exc.detail = 'The "%s" include query parameter failed to ' \
                             'validate with the following error(s): %s' \
                             % (include, exc.detail)
                excs.append(exc)

        if self.strict_mode and excs:
            raise ManyExceptions(excs)

    def validate_include(self, include, serializer):
        """ Validate each includeed query param individually

        Walk the serializers for deeply nested include requests
        to ensure they are allowed to be includeed.
        """

        relations = include.split(self.relation_sep)
        if len(relations) > self.max_relations:
            msg = 'Max relations limit of "%s" exceeded' % self.max_relations
            raise InvalidIncludeParam(msg)

        for idx, relation in enumerate(relations):
            _serializer = serializer.get_related_serializer(relation)
            includable = serializer.get_related_includable()

            if not _serializer or relation not in includable:
                raise InvalidIncludeParam('Missing or not allowed to include')

            related_path = '__'.join(relations[:idx + 1])
            self._update_cache(related_path, relation, _serializer)
            serializer = _serializer


class OrderingFilter(_OrderingFilter):
    """ Override default OrderingFilter to be JSON API compliant

    JSON API details
    ~~~~~~~~~~~~~~~~

    The JSON API spec reserves the `sort` query parameter for
    ordering.

    This filter can be used to support the `sort` query param
    for requesting ordering preferences on the primary data.

    This filter is JSON API compliant with the `sort` query
    parameter in the following mentionable ways:

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
    each sort is tested for eligibility.

    For a sort to be eligible it MUST meet all of the
    following criteria:

        1. The sort cannot be a relationship sort. That is not
           supported currently & is generally frowned upon.

        2. Be present in the list of the DRF superclasses
           `get_valid_fields` method
    """

    max_sorts = 3
    ordering_param = 'sort'
    relation_sep = '.'
    strict_mode = True

    def remove_invalid_fields(self, queryset, sorts, view):
        """ Override the default to support exception handling """

        allowed = [item[0] for item in self.get_valid_fields(queryset, view)]
        order = []
        excs = []

        if len(sorts) > self.max_sorts:
            msg = 'The sort query parameter requested "%s" ordering ' \
                  'preferences exceeding the max number of "%s"' \
                  % (len(sorts), self.max_sorts)
            raise InvalidSortParam(msg)

        for sort in sorts:
            if sort.lstrip('-') in allowed:
                order.append(sort)
            elif self.relation_sep in sort:
                msg = 'The "%s" sort query parameter is not allowed ' \
                      'due to unpredictable results when sorting on ' \
                      'relationships' % sort
                excs.append(InvalidSortParam(msg))
            else:
                msg = 'The "%s" sort query parameter either does not ' \
                      'exist or you are not allowed to sort on it' % sort
                excs.append(InvalidSortParam(msg))

        if excs and self.strict_mode:
            raise ManyExceptions(excs)
        return order


class SparseFilter(BaseFilterBackend):
    """ Support the limiting of responses to only specific fields

    This filter can be used to support the `fields` query param
    for requesting only a subset of fields to be returned on a
    resource type basis.

    Currently, this doesn't do any validation or limiting of
    the Django queryset. We could eventually use something like
    `defer()` but this could cause performance issues if not
    done properly. Instead, the pruning of fields is done by
    the serializer.
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
        a tuple value of fields to limit to.

        An example fields of `fields[actors]=name,movies` would
        return a dict of:

            {'actors': ['name', 'movies']}

        NOTE: the `id` & `type` members are always returned
              no matter the fields query param.
        """

        sparse_fields = {}
        regex = re.compile(r'^fields\[([A-Za-z0-9_]+)\]$')

        for param, val in request.query_params.items():
            match = regex.match(param)
            if match:
                vals = tuple(set(val.split(',') + ['id', 'type']))
                sparse_fields[match.groups()[0]] = vals
        return sparse_fields
