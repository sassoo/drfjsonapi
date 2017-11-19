"""
    drfjsonapi.renderers
    ~~~~~~~~~~~~~~~~~~~~~

    DRF renderer that is compliant with the JSON API spec
"""

from rest_framework.renderers import JSONRenderer


class JsonApiRenderer(JSONRenderer):
    """ JSON API compliant DRF renderer

    Inherit from the DRF JSONRenderer since JSON API is
    simply a structured representation of JSON.
    """

    media_type = 'application/vnd.api+json'

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
            'included': [],
            'jsonapi': {'version': '1.0'},
            'links': self.get_links(pager, renderer_context),
            'meta': pager.get('meta', {}),
        }
        return super().render(body, accepted_media_type, renderer_context)
