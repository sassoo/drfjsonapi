"""
    drfjsonapi.relations
    ~~~~~~~~~~~~~~~~~~~~~

    DRF relationship fields to assist with a JSON API spec
    compliant API.
"""

from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils.translation import ugettext_lazy as _
from rest_framework.relations import (
    MANY_RELATION_KWARGS,
    ManyRelatedField,
    PrimaryKeyRelatedField,
)


class ManyResourceRelatedField(ManyRelatedField):
    """ Override of DRF's native ManyRelated Field """

    def get_attribute(self, instance):
        """ DRF override to avoid unwanted database queries

        Relationships must either be included or have linkage
        enabled otherwise the database query is skipped.
        """

        includes = self.context.get('includes', {})
        if self.field_name in includes or self.child_relation.linkage:
            return super().get_attribute(instance)
        return []


class ResourceRelatedField(PrimaryKeyRelatedField):
    """ JSON API related field for relationships

    This field can be used as a drop-in replacement for the
    DRF PrimaryKeyRelatedField.
    """

    default_error_messages = {
        'rtype_conflict': _('Incorrect resource type of "{given}". Only '
                            '"{rtype}" resource types are accepted'),
    }

    linkage = True
    related_view = None
    rtype = None

    def __init__(self, **kwargs):
        """ Process our custom attrs so DRF doesn't barf """

        attrs = ('linkage', 'related_view', 'rtype')
        for attr in attrs:
            val = kwargs.pop(attr, getattr(self, attr))
            setattr(self, attr, val)
        super().__init__(**kwargs)

    @classmethod
    def many_init(cls, *args, **kwargs):
        """ DRF override for a custom ManyRelated class

        DRF override to disable linkage on many relations unless
        overidden. This is to avoid a bunch of potentially unwanted
        data which maybe resolved at a later date on demand
        """

        if 'linkage' not in kwargs:
            kwargs['linkage'] = False

        # begin - this is all ripped from DRF
        list_kwargs = {'child_relation': cls(*args, **kwargs)}
        for key in kwargs:
            if key in MANY_RELATION_KWARGS:
                list_kwargs[key] = kwargs[key]
        # end - this is all ripped from DRF
        return ManyResourceRelatedField(**list_kwargs)




    def get_data(self, value: str) -> dict:
        """ Return the relationships top-level `data` object

        Also known in the spec as "Resource Identifier" object
        for a single non-empty object only. This will not be
        called for empty valued relationships.

        The object looks like:

            {
                'id': '123',
                'type': 'actors',
            }

        :spec:
            jsonapi.org/format/#document-resource-identifier-objects
        """

        return {
            'id': value,
            'type': self.get_data_type(),
        }







    def get_links(self, parent_id: str) -> dict:
        """ Return the relationships top-level "links" object

        Currently, this only returns the `related` key or the
        "Related Resource Links" as cited in the JSON API spec.

        :spec:
            jsonapi.org/format/#document-resource-object-relationships
        """

        try:
            return {'related': reverse(self.related_view, args=[parent_id])}
        except NoReverseMatch:
            return {}

    def get_attribute(self, instance):
        """ DRF override XXX """

        # if self.linkage or included?
        # return get_attribute(instance, self.source_attrs)
        pass

    def get_rtype(self, instance: models.Model) -> str:
        """ Return the "Resource Identifier" type member

        :spec:
            jsonapi.org/format/#document-resource-identifier-objects
            jsonapi.org/format/#document-resource-object-identification
        """

        assert type(self.rtype) is str, 'rtype must be a str'
        return self.rtype

    def to_internal_value(self, data: dict):
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







    def to_representation(self, value):
        """ Override DRF PrimaryKeyRelatedField `to_representation` """

        # some how we need the instance but only if linkage=True or included
        # so get_rtype can have the instance
        rid = super().to_representation(value)
        if rid is not None:
            return self.get_data(str(rid))


class ProcessorRelatedField:
    queryset = Processor.objects.all()

    def get_rtype(self, instance):
        return '%s-processors' % instance.vendor



class ResourceIdentifierField:
    def get_attribute(self, instance):
        """ DRF override XXX """

        # if self.linkage or included?
        # return get_attribute(instance, self.source_attrs)
        pass

    def get_rtype(self, instance: models.Model) -> str:
        """ Return the "Resource Identifier" type member

        :spec:
            jsonapi.org/format/#document-resource-identifier-objects
            jsonapi.org/format/#document-resource-object-identification
        """

        assert type(self.rtype) is str, 'rtype must be a str'
        return self.rtype

    def to_internal_value(self, data: dict):
        """ DRF override during deserialization

        XXX Pass in the data as a resource identifier object:

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

    def to_representation(self, value):
        """ Override DRF PrimaryKeyRelatedField `to_representation` """

        # some how we need the instance but only if linkage=True or included
        # so get_rtype can have the instance
        rid = super().to_representation(value)
        if rid is not None:
            return self.get_data(str(rid))
