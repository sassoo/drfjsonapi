"""
    drfjsonapi.renderers
    ~~~~~~~~~~~~~~~~~~~~~

    DRF renderer that is compliant with the JSON API spec
"""

from collections import Iterable
from rest_framework.renderers import JSONRenderer
from .utils import _get_related_field


class JsonApiRenderer(JSONRenderer):
    """ JSON API compliant DRF renderer

    Inherit from the DRF JSONRenderer since JSON API is
    simply a structured representation of JSON.
    """

    media_type = 'application/vnd.api+json'

    def get_included(self, data, context: dict) -> list:
        """ Return the top level "Included Resources" array

        This should return a list that is compliant with the
        "Resource Objects" section of the JSON API spec.

        Since these are the compound documents to be "sideloaded"
        there should be no duplicates within the included array
        itself or the primary data.

        TIP: read the documentation of the `IncludeFilter`
             class for more information.
        """

        def table_key(resource):
            """ Generate a key from serialized `id` & `type` """

            return '_'.join((resource['id'], resource['type']))

        request, view = context['request'], context['view']

        if not data or not hasattr(request, 'includes'):
            return []

        # if single then coerce into list
        models = data.serializer.instance
        if not isinstance(models, Iterable):
            models = [models]
            data = [data]

        primary_cache = {table_key(d): d for d in data}
        include_cache = {}

        for model in models:
            for field in request.includes:
                rels = _get_related_field(model, field)
                if not rels:
                    continue
                elif not isinstance(rels, Iterable):
                    rels = [rels]

                serializer = view.includable_fields[field]
                serializer = serializer(context=context)

                for rel in rels:
                    val = serializer.to_representation(rel, skip_includes=True)
                    if table_key(val) not in primary_cache:
                        include_cache[table_key(val)] = val

        return include_cache.values()

    def get_jsonapi(self, context: dict) -> dict:
        """ Return the top level "JSON API" object

        :spec:
            jsonapi.org/format/#document-jsonapi-object
        """

        return {'version': '1.0'}

    def get_links(self, pager: dict, context: dict) -> dict:
        """ Return the top level "Links" object

        According to the JSON API spec this should include
        the required pagination links.

        :spec:
            jsonapi.org/format/#document-links
            jsonapi.org/format/#fetching-pagination
        """

        links = {'self': context['request'].get_full_path()}
        links.update(pager.get('links', {}))
        return links

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """ DRF override & entry point

        `data` can be quite a few different data formats unforutnately.
        It could be a single resource dict, None (no single resource),
        an array of many resource dicts with paging info, an empty array,
        or an "Errors" object.
        """

        if data and 'errors' in data:
            return super().render(data, accepted_media_type, renderer_context)

        try:
            data, pager = data['results'], data['pager']
        except (KeyError, TypeError):
            pager = {}

        body = {
            'data': data,
            'included': self.get_included(data, renderer_context),
            'jsonapi': self.get_jsonapi(renderer_context),
            'links': self.get_links(pager, renderer_context),
            'meta': pager.get('meta', {}),
        }
        return super().render(body, accepted_media_type, renderer_context)
