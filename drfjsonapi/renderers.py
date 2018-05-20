"""
    drfjsonapi.renderers
    ~~~~~~~~~~~~~~~~~~~~

    DRF renderer that is compliant with the JSON API spec
"""

from rest_framework.renderers import JSONRenderer


class JsonApiRenderer(JSONRenderer):
    """ JSON API compliant DRF renderer

    Inherit from the DRF JSONRenderer since JSON API is simply a
    structured representation of JSON.
    """

    media_type = 'application/vnd.api+json'

    def get_included(self, data, context) -> list:
        """ Return the top level "Included Resources" array

        This should return a list that is compliant with the
        "Resource Objects" section of the JSON API spec.
        """

        try:
            return context['view'].get_included(data.serializer)
        except (AttributeError, KeyError):
            return []

    def get_links(self, pager, context) -> dict:
        """ Return the top level "Links" object

        According to the JSON API spec this should include the
        required pagination links.

        :spec:
            jsonapi.org/format/#document-links
            jsonapi.org/format/#fetching-pagination
        """

        links = pager.get('links', {})
        if context and context.get('request'):
            links['self'] = context.get('request').get_full_path()
        return links

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """ DRF override & entry point

        `data` can be quite a few different data formats unforutnately.

        It could be a single resource dict, None (no single resource),
        an array of many resource dicts with paging info, an empty array,
        or an "Errors" object.
        """

        try:
            status = renderer_context['response'].status_code
            if status <= 199 or status == 204:
                return super().render(data, accepted_media_type, renderer_context)
        except(AttributeError, KeyError, TypeError):
            pass

        if data and 'errors' in data:
            return super().render(data, accepted_media_type, renderer_context)

        try:
            data, pager = data['results'], data['pager']
        except (KeyError, TypeError):
            pager = {}

        body = {
            'data': data,
            'included': self.get_included(data, renderer_context),
            'jsonapi': {'version': '1.0'},
            'links': self.get_links(pager, renderer_context),
            'meta': pager.get('meta', {}),
        }

        return super().render(body, accepted_media_type, renderer_context)
