"""
    drfjsonapi.relations
    ~~~~~~~~~~~~~~~~~~~~~

    DRF relationship fields to assist with a JSON API spec
    compliant API.
"""

from .utils import _get_resource_url, _get_url
from django.utils.translation import ugettext_lazy as _
from rest_framework.relations import (
    ManyRelatedField,
    PrimaryKeyRelatedField,
)


def _get_field_name(field):
    """ Return the fields name """

    return field.field_name or field.parent.field_name


def _get_field_serializer(field):
    """ Return the fields serializer """

    if isinstance(field.parent, ManyRelatedField):
        return field.parent.parent
    else:
        return field.parent


class ResourceRelatedField(PrimaryKeyRelatedField):
    """ JSON API related field for relationships

    This field can be used as a drop-in replacement for the
    DRF PrimaryKeyRelatedField.
    """

    default_error_messages = {
        'invalid': _('Invalid syntax. Relationship assignment requires a dict '
                     'with type & id keys is required'),
        'rtype_conflict': _('Incorrect resource type of "{given}". Only '
                            '"{rtype}" resource types are accepted'),
    }

    def __init__(self, related_view_name=None, rtype=None, **kwargs):

        super(ResourceRelatedField, self).__init__(**kwargs)

        self.related_view_name = related_view_name
        self.rtype = rtype
        assert rtype is not None, 'The `rtype` argument is required.'

    def get_data(self, rid):
        """ Return the relationships "Resource Linkage" object

        This should return a dict that is compliant with the
        "Resource Linkage" section of the JSON API spec. More
        precisely, the contents of a relationships top level
        `data` member.

        Since DRF calls each items `to_representation` method
        this method follows the "single Resource Identifier
        Object" section of the spec, only. That means return
        `None` (JSON API `null`) if the relationship is not set.

        :spec:
            jsonapi.org/format/#document-resource-object-linkage
            jsonapi.org/format/#document-resource-identifier-objects
        """

        if rid:
            return {
                'id': str(rid),
                'meta': self.get_data_meta(rid),
                'type': self.rtype,
            }

    def get_data_meta(self, rid):
        """ Return the "Resource Identified Object" meta dict

        Include the absolute URL for convenience of the resource.
        This, like all meta objects, in the JSON API spec is
        totally custom.

        :spec:
            jsonapi.org/format/#document-resource-identifier-objects
        """

        url = _get_resource_url(self.rtype, rid, self.context)
        return {'self': url}

    def get_links(self, parent_rid):
        """ Return the relationships "Links" object

        This should return a dict that is compliant with the
        "Resource Object Relationships" links section of the
        JSON API spec.

        Currently, this only returns the `related` key or the
        "Related Resource Links" as cited in the JSON API spec.

        In the future, the "Relationship Link" will be added.

        :spec:
            jsonapi.org/format/#document-resource-object-relationships
        """

        data = {}

        related_url = self.get_links_related(parent_rid)
        if related_url:
            data['related'] = related_url
        return data

    def get_links_related(self, parent_rid):
        """ Return the relationships "Related Resource Link" url

        This URL is used to get the relationships resource(s)
        as primary data.

        :spec:
            jsonapi.org/format/#document-resource-object-related-resource-links
        """

        kwargs = {'pk': parent_rid}
        view_name = self.get_links_related_view_name()
        return _get_url(view_name, self.parent.context, kwargs=kwargs)

    def get_links_related_view_name(self):
        """ Return the DRF view name for the "Related Resource Link"

        If not provided vai the `related_view_name` property then
        attempt to auto-determine it. The default view name is:

            <serializer rtype>-<field name>

        An example, of actors serializer with a movies relationship
        would have a default view name of: `actors-movies`
        """

        view_name = self.related_view_name
        if not view_name:
            view_name = '{rtype}-{field_name}'.format(
                field_name=_get_field_name(self),
                rtype=_get_field_serializer(self).get_rtype(),
            )
        return view_name

    def get_meta(self):
        """ Return the relationships "Meta" object """

        return {}

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
        """

        try:
            rid = data['id']
            rtype = data['type']
        except (KeyError, TypeError):
            self.fail('invalid')

        if self.rtype != rtype:
            self.fail('rtype_conflict', given=rtype, rtype=self.rtype)
        return super(ResourceRelatedField, self).to_internal_value(rid)

    def to_representation(self, value):
        """ Override DRF PrimaryKeyRelatedField `to_representation` """

        rid = super(ResourceRelatedField, self).to_representation(value)
        return self.get_data(rid)
