"""
    drfjsonapi.includesets
    ~~~~~~~~~~~~~~~~~~~~~~

    Interface for handling the JSON API include query parameters.
"""

import copy
import itertools

from .exceptions import InvalidIncludeParam
from .utils import _get_related_field


class JsonApiIncludeSet:
    """ This should be subclassed by custom IncludeSets """

    includable_fields = {}
    max_params = 15

    def __init__(self, context=None):
        """ Context will include the request & view """

        self.context = copy.copy(context) or {}

    def filter_queryset(self, queryset, include):
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

    def to_representation(self, instance):
        """ Return the JSON API include array

        `instance` could be an empty array, non-empty array of models
        or even a single non-iterable model instance.
        """

        def _update_cache(model):
            """ XXX """

            for field in include:
                serializer = self.includable_fields[field]
                rels = _get_related_field(model, field)
                if rels:
                    try:
                        include_cache[serializer].update(rels)
                    except TypeError:
                        include_cache[serializer].add(rels)

        if not instance:
            return []

        try:
            include = self.context['request'].jsonapi_include
        except (AttributeError, KeyError):
            return []

        # this basically uniquifies duplicate serializers & items
        # by using the serializer as a key & set as value
        include_cache = {
            serializer: set()
            for field, serializer in self.includable_fields.items()
        }

        try:
            for model in instance:
                _update_cache(model)
        except TypeError:
            _update_cache(instance)

        included = [
            serializer(context=self.context, many=True).to_representation(models)
            for serializer, models in include_cache.items()
        ]
        return list(itertools.chain(*included))

    def validate(self, include):
        """ Hook to validate the coerced include """

        if len(include) > self.max_params:
            msg = 'The request has "%s" include query parameters which ' \
                  'exceeds the max number of "%s" that can be requested.' \
                  % (len(include), self.max_params)
            raise InvalidIncludeParam(msg)

        for name in include:
            if name not in self.includable_fields:
                msg = 'The "%s" include query parameter is not supported ' \
                      'by this endpoint.' % name
                raise InvalidIncludeParam(msg)
        return include
