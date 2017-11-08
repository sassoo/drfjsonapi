"""
    drfjsonapi.relations
    ~~~~~~~~~~~~~~~~~~~~~

    DRF relationship fields to assist with a JSON API spec
    compliant API.
"""

from django.db import models
from django.utils.translation import ugettext_lazy as _
from rest_framework.relations import SlugRelatedField


class ResourceRelatedField(SlugRelatedField):
    """ JSON API related field for relationships """

    default_error_messages = {
        'rtype_conflict': _('Incorrect resource type of "{given}". Only '
                            '"{rtype}" resource types are accepted'),
    }

    def __init__(self, slug_field='id', **kwargs):
        """ Process our custom attrs so DRF doesn't barf """

        self.rtype = kwargs.pop('rtype', None)
        super().__init__(**kwargs)

    def get_rtype(self, instance: models.Model) -> str:
        """ Return the "Resource Identifier" type member

        :spec:
            jsonapi.org/format/#document-resource-identifier-objects
            jsonapi.org/format/#document-resource-object-identification
        """

        assert isinstance(self.rtype, str), 'rtype must be a str'
        return self.rtype

    def to_internal_value(self, data: dict) -> models.Model:
        """ DRF override during deserialization

        A JSON API normalized relationship will have the following
        members at a minimum:

            {
                'id': '123',
                'type': 'actors',
            }
        """

        rid, rtype = data['id'], data['type']
        # raises exc if not found, instance guaranteed
        instance = super().to_internal_value(rid)

        _rtype = self.get_rtype(instance)
        if _rtype != rtype:
            self.fail('rtype_conflict', given=rtype, rtype=_rtype)
        return instance

    def to_representation(self, obj: models.Model) -> dict:
        """ DRF override during serialization

        This won't be called unless included by parent serializer
        """

        return {
            'id': str(super().to_representation(obj)),
            'type': self.get_rtype(obj),
        }


# class ProcessorRelatedField:
#     queryset = Processor.objects.all()

#     def get_rtype(self, instance):
#         return '%s-processors' % instance.vendor
