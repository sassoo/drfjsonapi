"""
    drfjsonapi.filters
    ~~~~~~~~~~~~~~~~~~~

    DRF relationship fields to assist with a JSON API spec
    compliant API.
"""

import itertools
import re

from django.db.models import Q
from rest_framework.exceptions import ValidationError
from rest_framework.filters import BaseFilterBackend, OrderingFilter

from .exceptions import InvalidFilterParam, InvalidIncludeParam, InvalidSortParam
from .utils import _get_relationship, _to_set


class JsonApiBackend(object):
    """ For easy `isinstance` checks """
    pass


class JsonApiFieldFilter(JsonApiBackend, BaseFilterBackend):
    """ Support the filtering of arbitrary resource fields """

    fields = {}
    max_params = 15

    def filter_queryset(self, request, queryset, view):
        """ DRF entry point into the custom FilterBackend """

        filters = self.to_internal_value(request)
        filters = self.validate(filters)
        return self.apply_filter(queryset, filters)

    def apply_filter(self, queryset, filters):
        """ Turn the vetted query param filters into Q object expressions """

        q_filter = Q()
        for param, value in filters.items():
            q_filter.add(Q((param, value)), Q.AND)
        return queryset.filter(q_filter)

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
            validator = self.fields[field]
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


class JsonApiIncludeFilter(JsonApiBackend, BaseFilterBackend):
    """ Support the inclusion of compound documents

    The santizied includes query params will be available on the
    request object via a `jsonapi_include` attribute.
    """

    fields = {}
    max_params = 15

    def filter_queryset(self, request, queryset, view):
        """ DRF entry point into the custom FilterBackend """

        include = self.to_internal_value(request)
        include = self.validate(include)
        request.jsonapi_include = include
        return self.apply_filter(queryset, include)

    def apply_filter(self, queryset, include):
        """ Return a filtered queryset for the query params """

        return queryset.prefetch_related(*include)

    def to_internal_value(self, request):
        """ Return the sanitized `include` query parameters

        Handles comma separated & multiple include params & returns
        a tuple of duplicate free strings
        """

        include = request.query_params.getlist('include')
        include = (name.split(',') for name in include)
        include = list(itertools.chain(*include))
        return tuple(set(include))

    def to_representation(self, serializer, context=None):
        """ Return the JSON API include array """

        try:
            include = context['request'].jsonapi_include
        except (AttributeError, KeyError, TypeError):
            include = []

        if not include or not serializer.instance:
            return []

        # uniqifies duplicate serializers & models by using
        # the serializer as a key & set as value
        icache = {v: set() for k, v in self.fields.items()}
        models = _to_set(serializer.instance)

        for model in models:
            for field in include:
                cache_set = icache[self.fields[field]]
                cache_set.update(_to_set(_get_relationship(model, field)))

        # prune dupes in the include cache that are also present
        # in the primary data.
        _class = serializer.__class__
        if _class in icache:
            icache[_class] = icache[_class].difference(models)

        return [
            serializer(context=context).to_representation(model)
            for serializer, models in icache.items() for model in models
        ]

    def validate(self, include):
        """ Hook to validate the coerced include """

        if len(include) > self.max_params:
            msg = 'The request has "%s" include query parameters which ' \
                  'exceeds the max number of "%s" that can be requested.' \
                  % (len(include), self.max_params)
            raise InvalidIncludeParam(msg)

        for name in include:
            if name not in self.fields:
                msg = 'The "%s" include query parameter is not supported ' \
                      'by this endpoint.' % name
                raise InvalidIncludeParam(msg)
        return include


class JsonApiSortFilter(JsonApiBackend, OrderingFilter):
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
