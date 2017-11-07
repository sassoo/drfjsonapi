"""
    drfjsonapi.relations
    ~~~~~~~~~~~~~~~~~~~~~

    DRF relationship fields to assist with a JSON API spec
    compliant API.
"""

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

    include = False
    linkage = True
    related_view = None
    rtype = None

    def __init__(self, **kwargs):
        """ Process our custom attrs so DRF doesn't barf """

        attrs = ('include', 'linkage', 'related_view', 'rtype')
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
                'meta': {},
            }

        :spec:
            jsonapi.org/format/#document-resource-identifier-objects
        """

        return {
            'id': value,
            'meta': self.get_data_meta(),
            'type': self.get_data_type(),
        }

    def get_data_meta(self) -> dict:
        """ Return the "Resource Identifier" object meta object

        :spec:
            jsonapi.org/format/#document-resource-identifier-objects
            jsonapi.org/format/#document-meta
        """

        return {}

    def get_data_type(self) -> str:
        """ Return the "Resource Identifier" type member

        :spec:
            jsonapi.org/format/#document-resource-identifier-objects
            jsonapi.org/format/#document-resource-object-identification
        """

        # XXX is self.get_rtype() needed? what context would
        # it have to alter behavior? it wouldn't know the value
        # of the field or anything at all about what's being passed through
        assert type(self.rtype) is str, 'rtype must be a str'
        return self.rtype

    def get_meta(self) -> dict:
        """ Return the relationships top-level `meta` object

        :spec:
            jsonapi.org/format/#document-resource-object-relationships
            jsonapi.org/format/#document-meta
        """

        return {}






    def get_links(self, parent_id: str) -> dict:
        """ Return the relationships top-level "links" object

        Currently, this only returns the `related` key or the
        "Related Resource Links" as cited in the JSON API spec.

        :spec:
            jsonapi.org/format/#document-resource-object-relationships
        """

        related_url = self.get_links_related(parent_id)
        if related_url:
            return {'related': related_url}
        return {}

    def get_links_related(self, parent_id: str) -> str:
        """ Return the relationships "Related Resource Link"

        This URL is used to get the relationships resource(s)
        as primary data.

        :spec:
            jsonapi.org/format/#document-resource-object-related-resource-links
        """

        try:
            return reverse(self.related_view, args=[parent_id])
        except NoReverseMatch:
            return None










    def to_internal_value(self, data):
        """ Override DRF PrimaryKeyRelatedField `to_internal_value`

        If the relationship is set then `data` should be a dict
        containing at a minimum:

            {
                'id': <id>,
                'type': self.rtype,
            }

        however if the relationship is not set it will simply
        be None.

        The spec is not clear if a 409 is required when the type
        doesn't match the expected rtype of the relationship
        like it is with the primary resource object. We return
        a 422 because it works better with DRF. This may change.
        """

        # XXX all this should do is pass the rtype to validate_rtype
        # to make sure it's valid? how would an override know if it's valid?
        # wouldn't it need to know the id as well so it could look up something?
        #
        # it looks like DRF PrimaryKeyRelated will return the instance
        # natively so that could be passed to determine!!
        try:
            rid, rtype = data['id'], data['type']
            if self.rtype != rtype:
                self.fail('rtype_conflict', given=rtype, rtype=self.rtype)
        except (KeyError, TypeError):
            rid = None
        return super().to_internal_value(rid)

    def to_representation(self, value):
        """ Override DRF PrimaryKeyRelatedField `to_representation` """

        # XXX all this should do is something simple with meta
        # overrides maybe?
        rid = super().to_representation(value)
        if rid is not None:
            return self.get_data(str(rid))

    def validate_rtype(self, rtype):
        """ XXX """

        if self.get_rtype() != rtype:
            self.fail('rtype_conflict', given=rtype, rtype=self.get_rtype())
