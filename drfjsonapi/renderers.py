"""
    drfjsonapi.renderers
    ~~~~~~~~~~~~~~~~~~~~~

    DRF renderer that is compliant with the JSON API spec
"""

from collections import Iterable, OrderedDict
from rest_framework.renderers import JSONRenderer
from .utils import _get_related_field


class JsonApiRenderer(JSONRenderer):
    """ JSON API compliant DRF renderer

    Inherit from the DRF JSONRenderer since JSON API is
    simply a structured representation of JSON.
    """

    media_type = 'application/vnd.api+json'

    def get_errors(self, data):
        """ Return an array of "Error" objects

        :spec:
            jsonapi.org/format/#errors
        """

        return data

    # pylint: disable=too-many-arguments
    def _get_include(self, fields, model, include_table):
        """ Populate the included table for future processing

        This is a self-referential walking of the cache tree
        that was created by the `IncludeFilter`. It will add
        each model by serializer type & primary key to the
        include table so no dupes are present.

        It does not return anything & instead has mutation
        side-effects of the include table.

        NOTE: the serializer for each included model needs
              to know which fields will be included so
              proper data linkage can occur.

              This is done via the context
        """

        include_fields = [f for f in fields.keys() if f != 'serializer']
        for field in include_fields:
            relations = _get_related_field(model, field)
            if not relations:
                continue
            elif not isinstance(relations, Iterable):
                relations = [relations]

            for relation in relations:
                relation_fields = [
                    f for f in fields[field].keys()
                    if f != 'serializer'
                ]
                serializer = fields[field]['serializer']
                rtype = serializer.get_rtype()
                include_table['%s_%s' % (relation.pk, rtype)] = (
                    relation, serializer, relation_fields
                )
                self._get_include(fields[field], relation, include_table)

    def get_included(self, resources, request):
        """ Return the top level "Included Resources" array

        This should return a list that is compliant with the
        "Resource Objects" section of the JSON API spec.

        Since these are the compound documents to be "sideloaded"
        there should be no duplicates within the included array
        itself or the primary data.

        The drfjsonapi `IncludeFilter` adds a private property
        to the request object named `_includes` which greatly
        reduces the complexity of this process.

        TIP: read the documentation of the `IncludeFilter`
             class for more information.
        """

        # could be single model or many or serializer is None
        # if single then coerce into list
        models = getattr(resources.serializer, 'instance', None)
        if models and not isinstance(models, list):
            models = [models]

        if not all((resources, models, hasattr(request, '_includes'))):
            return []
        # could be a ReturnDict or ReturnList but coerce
        # into list so simple 'in' checks can work later
        elif resources and not isinstance(resources, list):
            resources = [resources]

        primary_table = {'%s_%s' % (r['id'], r['type']): r for r in resources}
        include_table = {}
        for model in models:
            self._get_include(request._includes, model, include_table)

        # serialize everything in included not in primary data
        included = []
        for key, val in include_table.items():
            if key not in primary_table:
                model, serializer, fields = val
                serializer.context['includes'] = fields
                included.append(serializer.to_representation(model))
        return included

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
        results otherwise it's empty.
        """

        return pager.get('meta', {})

    def get_top_level(self, data, request, pager):
        """ Return the "Top Level" object of the resource(s)

        This should return a dict that is compliant with the
        "Top Level" section of the JSON API spec.

        :spec:
            jsonapi.org/format/#document-top-level
        """

        return {
            'data': data,
            'included': self.get_included(data, request),
            'jsonapi': self.get_jsonapi(),
            'links': self.get_links(request, pager),
            'meta': self.get_meta(pager),
        }

    def render(self, data, media_type=None, renderer_context=None):
        """ DRF entry point

        `data` can be quite a few different data formats
        unforutnately. It could be a single resource dict,
        None (no single resource), an array of many resource
        dicts with paging info, an empty array, or an "Errors"
        object.

        This should be handled better somehow I'd imagine.
        """

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
            data = self.get_top_level(data, request, pager)

        return super(JsonApiRenderer, self).render(
            data,
            media_type,
            renderer_context,
        )
