"""
    drfjsonapi.schemas
    ~~~~~~~~~~~~~~~~~~

    DRF schemas to assist with parsing currently.
"""


DEFINITIONS = {
    'links': {
        'description': 'JSON API "links" member, when used MUST be a JSON object '
                       'whose members MUST contain valid JSON',
        'uri': 'http://jsonapi.org/format/#document-meta',
        'type': 'object',
        'additionalProperties': True,
    },
    'meta': {
        'description': 'JSON API "meta" member, when used MUST be a JSON object '
                       'whose members MUST contain valid JSON',
        'uri': 'http://jsonapi.org/format/#document-meta',
        'type': 'object',
        'additionalProperties': True,
    },
    'relationshipLinkage': {
        'description': 'JSON API relationship resource linkages MUST be a JSON '
                       'object with a required "data" member representing the '
                       'resource linkage when setting relationships.',
        'uri': 'http://jsonapi.org/format/#document-resource-object-linkage',
        'type': 'object',
        'required': [
            'data',
        ],
        'properties': {
            'data': {
                'description': 'JSON API relationship resource linkages MUST '
                               'be represented as "null" for empty to-one, an '
                               'empty array ([]) for empty to-many, a single '
                               'resource identifier object for a non-empty to-one, '
                               'or an array of resource identifier objects for '
                               'non-empty to-many relationships.',
                'uri': 'http://jsonapi.org/format/#document-resource-object-linkage',
                'type': [
                    'array',
                    'null',
                    'object',
                ],
                'oneOf': [
                    {'$ref': '#/definitions/relationshipToMany'},
                    {'$ref': '#/definitions/relationshipToOne'},
                ],
            },
            'meta': {
                '$ref': '#/definitions/meta',
            },
        },
        'additionalProperties': False,
    },
    'relationshipToMany': {
        'description': 'JSON API to-many relationships should be an empty array '
                       '([]) or an array of objects each containing "type" and '
                       '"id" members representing a "resource identifier object".',
        'uri': 'http://jsonapi.org/format/#document-resource-object-linkage',
        'type': 'array',
        'items': {
            '$ref': '#/definitions/resourceIdentifier'
        },
        'uniqueItems': True,
    },
    'relationshipToOne': {
        'description': 'JSON API to-one relationships should be null or a single '
                       'object containing "type" and "id" members representing a '
                       '"resource identifier object".',
        'uri': 'http://jsonapi.org/format/#document-resource-object-linkage',
        'type': [
            'null',
            'object',
        ],
        'oneOf': [
            {'$ref': '#/definitions/resourceIdentifier'},
            {'type': 'null'},
        ],
    },
    'resource': {
        'description': 'JSON API resource objects MUST be a JSON object with '
                       'a required "data" member representing the primary data.',
        'uri': 'http://jsonapi.org/format/#document-top-level',
        'type': 'object',
        'required': [
            'data',
        ],
        'properties': {
            'data': {
                '$ref': '#/definitions/resourceObject',
            },
            'meta': {
                '$ref': '#/definitions/meta',
            },
        },
        'additionalProperties': False,
    },
    'resourceIdentifier': {
        'description': 'JSON API resource identifier objects MUST be a JSON '
                       'object containing the required "id" & "type" members '
                       'with string values',
        'uri': 'http://jsonapi.org/format/#document-resource-identifier-objects',
        'type': 'object',
        'required': [
            'id',
            'type',
        ],
        'properties': {
            'type': {
                '$ref': '#/definitions/resourceIdentifierType',
            },
            'id': {
                '$ref': '#/definitions/resourceIdentifierId',
            },
            'meta': {
                '$ref': '#/definitions/meta',
            },
        },
        'additionalProperties': False,
    },
    'resourceIdentifierId': {
        'description': 'JSON API resource identifier "id" member MUST be a string',
        'uri': 'http://jsonapi.org/format/#document-resource-object-identification',
        'type': 'string',
    },
    'resourceIdentifierType': {
        'description': 'JSON API resource identifier "type" member MUST be a string',
        'uri': 'http://jsonapi.org/format/#document-resource-object-identification',
        'type': 'string',
    },
    'resourceObject': {
        'description': 'JSON API resource objects MUST be a JSON object containing '
                       'the top-level "id" & "type" members with string values',
        'uri': 'http://jsonapi.org/format/#document-resource-objects',
        'type': 'object',
        'required': [
            'type',
        ],
        'properties': {
            'id': {
                '$ref': '#/definitions/resourceIdentifierId',
            },
            'type': {
                '$ref': '#/definitions/resourceIdentifierType',
            },
            'attributes': {
                '$ref': '#/definitions/resourceObjectAttributes',
            },
            'relationships': {
                '$ref': '#/definitions/resourceObjectRelationships',
            },
            'links': {
                '$ref': '#/definitions/links',
            },
            'meta': {
                '$ref': '#/definitions/meta',
            },
        },
        'additionalProperties': False,
    },
    'resourceObjectAttributes': {
        'description': 'JSON API resource object "attributes" member MUST be a '
                       'JSON object. Its members MUST not contain any top-level '
                       'reserved names ("links", "relationships", "id", "type") '
                       'or names incompliant incompliant with the JSON API member'
                       'names section',
        'uri': 'http://jsonapi.org/format/#document-resource-object-attributes',
        'type': 'object',
        'patternProperties': {
            '^(?!relationships$|links$|id$|type$)\\w[-\\w_]*$': {},
        },
        'additionalProperties': False,
    },
    'resourceObjectRelationships': {
        'description': 'JSON API resource object "relationships" member MUST be a '
                       'JSON object.',
        'uri': 'http://jsonapi.org/format/#document-resource-object-relationships',
        'type': 'object',
        'patternProperties': {
            '^(?!id$|type$)\\w[-\\w_]*$': {
                'description': 'JSON API resource object "relationships" MUST not '
                               'not contain any top-level reserved names ("id", '
                               '"type") or names incompliant with the JSON API '
                               'member names section',
                'uri': 'http://jsonapi.org/format/#document-resource-object-relationships',
                '$ref': '#/definitions/relationshipLinkage',
            },
        },
        'additionalProperties': False,
    },
}


HEADER = {
    '$schema': 'http://json-schema.org/draft-04/schema#',
    'title': 'JSON API Schema',
    'description': 'This is a schema for requests in the JSON API format.',
    'uri': 'http://jsonapi.org/format',
    'definitions': DEFINITIONS,
}


RELATIONSHIP_LINKAGE_SCHEMA = {
    **HEADER,
    **{'$ref': '#/definitions/relationshipLinkage'},
}


RESOURCE_OBJECT_SCHEMA = {
    **HEADER,
    **{'$ref': '#/definitions/resource'},
}
