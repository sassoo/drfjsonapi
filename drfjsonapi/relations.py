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


def _get_attribute(inst, func):
    """ XXX """
    def wrapper(*args, **kwargs):
        """ XXX """
        queryset = func(*args, **kwargs)
        if hasattr(queryset, 'all') and inst.filter_backends:
            for backend in inst.filter_backends:
                queryset = backend().filter_queryset(
                    inst.context['request'],
                    queryset,
                    inst.context['view'],
                )
        return queryset
    return wrapper


def _get_field_name(field):
    """ Return the fields name """

    return field.field_name or field.parent.field_name


def _get_parent_serializer(field):
    """ Return the fields parent serializer """

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
    filter_backends = ()
    includable = False
    include = False
    linkage = False
    related_view = None
    rtype = None
    serializer = None

    def __new__(cls, *args, **kwargs):
        """ XXX override because of DRF ManyRelatedField

        * serializer needed if includable
        * includable needed if include
        """

        inst = super(ResourceRelatedField, cls).__new__(cls, *args, **kwargs)

        inst.filter_backends = kwargs.pop('filter_backends', ())
        inst.includable = kwargs.pop('includable', cls.includable)
        inst.include = kwargs.pop('include', cls.include)
        inst.linkage = kwargs.pop('linkage', cls.linkage)
        inst.related_view = kwargs.pop('related_view', cls.related_view)
        inst.rtype = kwargs.pop('rtype', cls.rtype)
        inst.serializer = kwargs.pop('serializer', cls.serializer)

        if not isinstance(inst, ResourceRelatedField):
            inst.child_relation.default_linkage = inst.rtype
            inst.child_relation.rtype = inst.rtype
            inst.get_attribute = _get_attribute(inst, inst.get_attribute)
        return inst

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
        view = self.get_links_related_view()
        return _get_url(view, self.parent.context, kwargs=kwargs)

    def get_links_related_view(self):
        """ Return the DRF view name for the "Related Resource Link"

        If not provided via the `related_view` property then
        attempt to auto-determine it. The default view name is:

            <serializer rtype>-<field name>

        An example, of actors serializer with a movies relationship
        would have a default view name of: `actors-movies`
        """

        view = self.related_view
        if not view:
            view = '{rtype}-{field_name}'.format(
                field_name=_get_field_name(self),
                rtype=_get_parent_serializer(self).get_rtype(),
            )
        return view

    def get_meta(self):
        """ Return the relationships "Meta" object

        This is the relationships top-level meta object & by
        default nothing except an empty object is returned.

        :spec:
            jsonapi.org/format/#document-resource-object-relationships
        """

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

        # if include return it
        # if linkage return it

        rid = super(ResourceRelatedField, self).to_representation(value)
        return self.get_data(rid)
