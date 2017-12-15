"""
    drfjsonapi.includesets
    ~~~~~~~~~~~~~~~~~~~~~~

    Interface for handling the JSON API include query parameters.
"""

import itertools

from .exceptions import InvalidIncludeParam
from .utils import _get_relationship, _to_set


class JsonApiIncludeSet:
    """ This should be subclassed by custom IncludeSets """

    fields = {}
    max_params = 15

    def __init__(self, context=None):
        """ Context will include the request & view """

        self.context = context or {}

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

    def to_representation(self, serializer):
        """ Return the JSON API include array """

        if not serializer.instance:
            return []

        try:
            include = self.context.get('request').jsonapi_include
        except AttributeError:
            return []

        # uniqifies duplicate serializers & models by using
        # the serializer as a key & set as value
        icache = {v: set() for k, v in self.fields.items()}
        models = _to_set(serializer.instance)

        for model in models:
            for field in include:
                cache_set = icache[self.fields[field]]
                relationships = _get_relationship(model, field)
                cache_set.update(_to_set(relationships))

        # prune dupes in the include cache that are also present
        # in the primary data.
        _class = serializer.__class__
        if _class in icache:
            icache[_class] = icache[_class].difference(models)

        included = (
            serializer(context=self.context, many=True).to_representation(models)
            for serializer, models in icache.items()
        )
        # flatten the list of lists
        return list(itertools.chain(*included))

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
