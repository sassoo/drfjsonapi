"""
    drfjsonapi.renderers
    ~~~~~~~~~~~~~~~~~~~~~

    DRF renderer that is compliant with the JSON API spec
"""

from collections import Iterable, OrderedDict
from rest_framework.relations import ManyRelatedField
from rest_framework.renderers import JSONRenderer


class JsonApiRenderer(JSONRenderer):
    """ JSON API compliant DRF renderer

    Inherit from the DRF JSONRenderer since JSON API is
    simply a structured representation of JSON.
    """

    media_type = 'application/vnd.api+json'

    def get_data(self, data, serializer):
        """ Return an individual "Resource Object" object

        This should return a dict that is compliant with the
        "Resource Object" section of the JSON API spec. It
        will later be wrapped by the "Top Level" members.

        :spec:
            jsonapi.org/format/#document-resource-objects
        """

        resource = {
            'meta': data.pop('meta'),
            'links': data.pop('links'),
            'type': data.pop('type'),
        }

        if data:
            resource['attributes'] = data
        relationships = self.get_data_relationships(data, serializer)
        if relationships:
            resource['relationships'] = relationships
        # wait to pop until the end
        resource['id'] = str(data.pop('id'))

        return resource

    def get_data_relationships(self, data, serializer):
        """ Return a resource objects "Relationships" object

        This should return a dict that is compliant with the
        "Relationships Object" section of the JSON API spec.
        Specifically, the contents of the top level `relationships`
        member of an individual resource boject.

        :spec:
            jsonapi.org/format/#document-resource-object-relationships
        """

        relationships = {}
        for key, field in serializer.fields.items():
            if isinstance(field, ManyRelatedField):
                field = field.child_relation
            # sparse fields
            if key not in data:
                continue
            try:
                relationships[key] = {
                    'links': field.get_links(data['id']),
                    'meta': field.get_meta(),
                    'data': data.pop(key),
                }
            except AttributeError:
                continue
        return relationships

    def get_errors(self, data):
        """ Return an array of "Error" objects

        Set the proper RFC 6901 JSON pointer object by checking
        the type of error. Global resource errors, field-level
        errors, & relationship field errors will have different
        error codes.

        The existing pointer will already be set but not yet
        fully qualified like it needs to be specifically for
        JSON API.

        :spec:
            jsonapi.org/format/#errors
        """

        for error in data['errors']:
            pointer = error['source']['pointer']

            if error['code'] == 'RelationshipError':
                error['source']['pointer'] = '/data/relationships%s' % pointer
            elif error['code'] == 'FieldError':
                error['source']['pointer'] = '/data/attributes%s' % pointer
            elif error['code'] == 'ResourceError':
                error['source']['pointer'] = '/data'
        return data

    def _get_include(self, cache, context, models, ret):
        """ Given a cache dict & models serialize them

        This is self-referential walking the cache tree that
        was created by the `InclusionFilter`. It ensure no
        dupes exist within the compound documents array but
        doesn't do anything with the primary data.

        It does not return anything & instead has mutation
        side-effects of the inclusion array `ret`.
        """

        field = cache['field']
        serializer = cache['serializer']

        for model in models:
            try:
                _models = getattr(model, field).all()
            except AttributeError:
                if not getattr(model, field):
                    continue
                _models = [getattr(model, field)]

            for _model in _models:
                _serializer = serializer(_model, context=context)
                data = self.get_data(_serializer.data, _serializer)

                # no dupes
                if data not in ret:
                    ret.append(data)

            for val in cache.values():
                if isinstance(val, dict):
                    self._get_include(val, context, _models, ret)

    def get_included(self, resources, serializer, request):
        """ Return the top level "Included Resources" array

        This should return a list that is compliant with the
        "Resource Objects" section of the JSON API spec.

        Since these are the compound documents to be "sideloaded"
        there should be no duplicates within the included array
        itself or the primary data.

        The drfjsonapi `InclusionFilter` adds a private property
        to the request object named `_inclusion_cache` which
        greatly reduces the complexity of this process.

        TIP: read the documentation of the `InclusionFilter`
             class for more information.

        :spec:
            jsonapi.org/format/#document-resource-objects
        """

        ret = []
        if not resources or not serializer.instance:
            return ret

        # could be single resource or many
        models = serializer.instance
        if not isinstance(models, Iterable):
            models = [models]

        for val in request._inclusion_cache.values():
            self._get_include(val, serializer.context, models, ret)

        # remove dupes from primary data
        return [data for data in ret if data not in resources]

    def get_jsonapi(self):
        """ Return the top level "JSON API" object

        Only the `version` member is valid.

        :spec:
            jsonapi.org/format/#document-jsonapi-object
        """

        return {'version': '1.0'}

    def get_links(self, request, pager):
        """ Return the top level "Links" object

        According to the JSON API spec this should include
        the required pagination links.

        :spec:
            jsonapi.org/format/#document-links
            jsonapi.org/format/#fetching-pagination
        """

        links = {'self': request.build_absolute_uri()}
        if pager:
            links.update(pager['links'])
        return links

    def get_meta(self, pager):
        """ Return the top level "Meta" object

        We include some helpful counters from the pagination
        results.
        """

        return pager.get('meta', {})

    def get_top_level(self, data, request, pager, serializer=None):
        """ Return the "Top Level" object of the resource(s)

        This should return a dict that is compliant with the
        "Top Level" section of the JSON API spec.

        :spec:
            jsonapi.org/format/#document-top-level
        """

        return {
            'data': data,
            'included': self.get_included(data, serializer, request),
            'jsonapi': self.get_jsonapi(),
            'links': self.get_links(request, pager),
            'meta': self.get_meta(pager),
        }

    def render(self, data, media_type=None, renderer_context=None):
        """ DRF entry point """

        pager = {}
        request = renderer_context['request']

        # list with drfjsonapi pager
        if isinstance(data, OrderedDict) and 'pager' in data:
            pager = data['pager']
            data = data['results']

        if not data:
            data = self.get_top_level(data, request, pager)
        elif 'errors' in data:
            data = self.get_errors(data)
        else:
            serializer = data.serializer
            if isinstance(data, list):
                serializer = serializer.child
                data = [self.get_data(d, serializer) for d in data]
            else:
                data = self.get_data(data, serializer)
            data = self.get_top_level(data, request, pager, serializer)

        return super(JsonApiRenderer, self).render(
            data,
            media_type,
            renderer_context,
        )
