"""
    drf_jsonapi.parsers
    ~~~~~~~~~~~~~~~~~~~

    DRF parser that is compliant with the JSON API
    specification.

    It's broken down into 2 parts:

        1. A parser for spec compliant validations
        2. A normalizer for converting into a common format
           expected by DRF serializers.
"""

from .renderers import JsonApiRenderer
from rest_framework import exceptions
from rest_framework.parsers import JSONParser


class JsonApiParser(JSONParser):
    """ JSON API compliant DRF parser

    Inherit from the DRF JSONParser since JSON API is simply
    a structured representation of JSON.
    """

    media_type = 'application/vnd.api+json'
    renderer_class = JsonApiRenderer

    def parse(self, stream, media_type=None, parser_context=None):
        """ Entry point invoked by DRF

        Order is important. Start from the request body root key
        & work your way down so exception handling is easier to
        follow.
        """

        req = parser_context['request']
        data = super(JsonApiParser, self).parse(
            stream,
            media_type,
            parser_context
        )

        self._parse_top_level(data)
        self._parse_resource(data['data'], req)

        data = data['data']

        if 'attributes' in data:
            self._parse_attributes(data['attributes'])
        if 'relationships' in data:
            self._parse_relationships(data['relationships'])

        return self.normalize(data)

    @staticmethod
    def _normalize_attributes(attributes):
        """ Get all the attributes by key/val & return them

        :param attributes:
            dict JSON API attributes object
        :return: dict
        """

        return attributes

    @staticmethod
    def _normalize_relationships(relationships):
        """ Get all the relationships by key/val & return them

        A normalized relationship dict uses the key name without
        any alteration but the value will be the `id` provided
        in the payload if present. If not present, then the client
        wants to unset the relationship so it will be set to None.

        INFO: only works for to-one relationships.

        :param relationships:
            dict JSON API relationships object
        :return: dict
        """

        ret = {}

        for key, val in relationships.items():
            if not val['data']:
                ret[key] = None
            else:
                ret[key] = val['data']['id']

        return ret

    def normalize(self, data):
        """ Invoke the JSON API normalizer

        This is done by flattenting the payloads attributes &
        relationships.

        We don't need to vet the inputs much because the Parser
        has already done all the work.

        :param data:
            the already vetted & parsed payload
        :return:
            normalized dict
        """

        if 'attributes' in data:
            attributes = data.pop('attributes')
            attributes = self._normalize_attributes(attributes)

            data.update(attributes)

        if 'relationships' in data:
            relationships = data.pop('relationships')
            relationships = self._normalize_relationships(relationships)

            data.update(relationships)

        return data

    def _parse_attributes(self, attributes):
        """ Ensure compliance with the spec's attributes section

        Specifically, the attributes object of the single resource
        object. This contains the key / values to be mapped to the
        model.

        :param attributes:
            dict JSON API attributes object
        """

        link = 'jsonapi.org/format/#document-resource-object-attributes'

        if not isinstance(attributes, dict):
            self.fail('The JSON API resource object attributes key MUST '
                      'be a hash.', link)

        if 'id' in attributes or 'type' in attributes:
            self.fail('A field name of `id` or `type` is not allowed in '
                      'the attributes object. They should be top-level '
                      'keys.', link)

    def _parse_relationships(self, relationships):
        """ Ensure compliance with the spec's relationships section

        Specifically, the relationships object of the single resource
        object. For modifications we only support relationships via
        the `data` key referred to as Resource Linkage.

        :param relationships:
            dict JSON API relationships object
        """

        link = 'jsonapi.org/format/#document-resource-object-relationships'

        if not isinstance(relationships, dict):
            self.fail('The JSON API resource object relationships key MUST '
                      'be a hash & comply with the spec\'s resource linkage '
                      'section.', link)

        for key, val in relationships.items():
            if not isinstance(val, dict) or 'data' not in val:
                self.fail('Relationship key %s MUST be a hash & contain '
                          'a `data` field compliant with the spec\'s '
                          'resource linkage section.' % key, link)

            if isinstance(val['data'], dict):
                data = val['data']
                rid = isinstance(data.get('id'), unicode)
                rtype = isinstance(data.get('type'), unicode)

                if not rid or not rtype:
                    self.fail('%s relationship\'s resource linkage MUST '
                              'contain `id` & `type` fields. Additionally, '
                              'they must both be strings.' % key, link)
            elif isinstance(val['data'], list):
                self.deny('Modifying the %s relationship or any to-many '
                          'relationships for that matter are is not '
                          'currently supported. Instead, modify the to-one '
                          'side directly.' % key, link)
            elif val['data']:
                self.fail('The relationship key %s is malformed & impossible '
                          'for us to understand your intentions. It MUST be '
                          'a hash & contain a `data` field compliant with '
                          'the spec\'s resource linkage section or null if '
                          'you want to unset the relationship.' % key, link)

    def _parse_resource(self, resource, req):
        """ Ensure compliance with the spec's resource objects section

        :param resource:
            dict JSON API resource object
        """

        link = 'jsonapi.org/format/#document-resource-objects'
        rid = isinstance(resource.get('id'), unicode)
        rtype = isinstance(resource.get('type'), unicode)

        if not rtype or (req.method in ('PATCH', 'PUT') and not rid):
            self.fail('JSON API requires that every resource object MUST '
                      'contain a `type` top-level key. Additionally, when '
                      'modifying an existing resource object an `id` '
                      'top-level key is required. The values of both keys '
                      'MUST be strings. Your request did not comply with '
                      'one or more of these 3 rules', link)

        if 'attributes' not in resource and 'relationships' not in resource:
            self.fail('Modifiying or creating resources require at minimum '
                      'an attributes object and/or relationship object.', link)

        if rid and req.method == 'POST':
            self.deny('Our API does not support client-generated ID\'s '
                      'when creating NEW resources. Instead, our API will '
                      'generate one for you & return it in the response.',
                      'jsonapi.org/format/#crud-creating-client-ids')

    def _parse_top_level(self, data):
        """ Ensure compliance with the spec's top-level section """

        link = 'jsonapi.org/format/#document-top-level'

        try:
            if not isinstance(data['data'], dict):
                raise TypeError
        except (KeyError, TypeError):
            self.fail('JSON API payloads MUST be a hash at the most '
                      'top-level; rooted at a key named `data` where the '
                      'value must be a hash. Currently, we only support '
                      'JSON API payloads that comply with the single '
                      'Resource Object section.', link)

        if 'errors' in data:
            self.fail('JSON API payloads MUST not have both `data` & '
                      '`errors` top-level keys.', link)

    @staticmethod
    def deny(detail, link=None):
        """ Fail with a PermissionDenied containing a link """

        exc = exceptions.PermissionDenied(detail)
        exc.link = link
        raise exc

    @staticmethod
    def fail(detail, link=None):
        """ Fail with a ParseError containing a link """

        exc = exceptions.ParseError(detail)
        exc.link = link
        raise exc
