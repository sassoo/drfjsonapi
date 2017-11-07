""" Blah blah """

from jsonschema import Draft4Validator
from jsonschema.exceptions import best_match

import schema

X = {
    'data': {
        'type': 'foo',
        'id': '1',
        'attributes': {'foo': '2'},
        'relationships': {
            'tags': {'foo': [{}]}
        },
    }
}

ERR = Draft4Validator(schema.RESOURCE_OBJECT_SCHEMA).iter_errors(X)
ERR = best_match(ERR)

print('RESOURCE OBJECT')
print()
print(ERR.message)
print()
print('/'.join(ERR.absolute_path))
print()
print(ERR.schema['description'])
print()


Y = {
    'foo': False
}


ERR = Draft4Validator(schema.RELATIONSHIP_LINKAGE_SCHEMA).iter_errors(Y)
ERR = best_match(ERR)

print('RELATIONSHIP')
print()
print(ERR.message)
print()
print(ERR.absolute_path)
print()
print(ERR.schema['description'])
print()
