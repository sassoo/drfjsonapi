"""
    drfjsonapi.relations
    ~~~~~~~~~~~~~~~~~~~~

    DRF relationship fields to assist with a JSON API spec
    compliant API.
"""

from django.utils.translation import ugettext_lazy as _
from rest_framework.relations import SlugRelatedField


class JsonApiRelatedField(SlugRelatedField):
    """ JSON API related field for relationships """

    default_error_messages = {
        'does_not_exist': _('Does not exist.'),
        'invalid': _('Invalid value.'),
        'invalid_rtype': _('Invalid resource type of "{given}".'),
    }

    def __init__(self, slug_field='id', **kwargs):
        """ Process our custom attrs so DRF doesn't barf """

        self.rtype = kwargs.pop('rtype', None)
        super().__init__(slug_field=slug_field, **kwargs)

    def get_rtype(self, instance):
        """ Return the "Resource Identifier" type member """

        return self.rtype

    def to_internal_value(self, data):
        """ DRF override during deserialization

        A JSON API normalized relationship will have the following
        members at a minimum:

            {
                'id': '123',
                'type': 'actors',
            }
        """

        try:
            rid, rtype = data['id'], data['type']
        except TypeError:
            self.fail('invalid')

        # raises exc if not found, instance guaranteed
        instance = super().to_internal_value(rid)

        _rtype = self.get_rtype(instance)
        if _rtype != rtype:
            self.fail('invalid_rtype', given=rtype)
        return instance

    def to_representation(self, obj):
        """ DRF override during serialization

        `to_representation` could return None if the relationship
        was cleared (OneToOne) & deleted but still present in
        memory.
        """

        ret = super().to_representation(obj)
        if ret is not None:
            return {
                'id': str(ret),
                'type': self.get_rtype(obj),
            }
        return None
