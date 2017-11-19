"""
    drfjsonapi.parsers
    ~~~~~~~~~~~~~~~~~~~

    DRF parsers that is compliant with the JSON API specification.

    It's broken down into 2 parts:

        1. A parser for spec compliant validations
        2. A normalizer for converting into a common format
           expected by DRF serializers.
"""

from jsonschema import Draft4Validator
from jsonschema.exceptions import best_match
from rest_framework.parsers import JSONParser

from .exceptions import InvalidBody
from .renderers import JsonApiRenderer
from .schema import (
    RELATIONSHIP_LINKAGE_SCHEMA,
    RESOURCE_OBJECT_SCHEMA,
)


def _validate_body(body: dict, schema: dict) -> None:
    """ Raise an InvalidBody exception if non-compliant with the spec """

    errors = Draft4Validator(schema).iter_errors(body)
    error = best_match(errors)
    if error:
        exc = InvalidBody(error.message)
        exc.link = error.schema['uri']
        exc.meta = {'spec': error.schema['description']}
        exc.source = {'pointer': '/' + '/'.join(error.absolute_path)}
        raise exc


class JsonApiRelationshipNormalizer:
    """ Normalize a JSON API relationship update compliant payload """

    def normalize(self, body: dict) -> dict:
        """ Entry point from the parser """

        raise NotImplementedError


class JsonApiRelationshipParser(JSONParser):
    """ JSON API "Updating Relationships" compliant DRF parser """

    media_type = 'application/vnd.api+json'
    renderer_class = JsonApiRenderer

    jsonapi_normalizer = JsonApiRelationshipNormalizer
    jsonapi_schema = RELATIONSHIP_LINKAGE_SCHEMA

    # pylint: disable=arguments-differ
    def parse(self, *args, **kwargs):
        """ DRF entry point """

        body = super().parse(*args, **kwargs)
        _validate_body(body, self.jsonapi_schema)
        return self.jsonapi_normalizer().normalize(body)


class JsonApiResourceNormalizer:
    """ Normalize a JSON API single "Resource Object" compliant payload """

    def normalize(self, body: dict) -> dict:
        """ Entry point from the parser

        Flatten the payloads attributes & relationships so DRF
        serializers work as expected.
        """

        data = {
            'id': body['data'].get('id'),
            'type': body['data']['type'],
            **body['data'].get('attributes', {}),
        }
        data.update({
            k: v['data']
            for k, v in body['data'].get('relationships', {}).items()
        })
        return data


class JsonApiResourceParser(JSONParser):
    """ JSON API single "Resource Object" compliant DRF parser """

    media_type = 'application/vnd.api+json'
    renderer_class = JsonApiRenderer

    jsonapi_normalizer = JsonApiResourceNormalizer
    jsonapi_schema = RESOURCE_OBJECT_SCHEMA

    # pylint: disable=arguments-differ
    def parse(self, *args, **kwargs):
        """ DRF entry point """

        body = super().parse(*args, **kwargs)
        _validate_body(body, self.jsonapi_schema)
        return self.jsonapi_normalizer().normalize(body)
