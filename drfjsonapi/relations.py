"""
    drfjsonapi.relations
    ~~~~~~~~~~~~~~~~~~~~~

    DRF relationship fields to assist with a JSON API spec
    compliant API.
"""

from django.utils.module_loading import import_string
from django.utils.translation import ugettext_lazy as _
from rest_framework.relations import (
    ManyRelatedField,
    PrimaryKeyRelatedField,
)
from .utils import _get_resource_url, _get_url


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
        'rtype_conflict': _('Incorrect resource type of "{given}". Only '
                            '"{rtype}" resource types are accepted'),
    }

    includable = False
    include = False
    linkage = True
    related_view = None
    serializer = None

    def __init__(self, **kwargs):
        """ Process our custom attrs so DRF doesn't barf """

        attrs = ('includable', 'include', 'linkage', 'related_view',
                 'serializer')
        for attr in attrs:
            val = kwargs.pop(attr, getattr(self, attr))
            setattr(self, attr, val)
        super().__init__(**kwargs)

    @property
    def rtype(self):
        """ Return the resource type from the relationships serializer """

        return self.get_serializer().get_rtype()

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

    def get_filtered_queryset(self):
        """ Override to use a filtered queyset

        DRF doesn't have a built-in method for passing or
        providing filters for related fields on a serializer.
        There are tickets about it & it's left to the app
        developers currently.

        This method will be called by the parent serializer
        to be used in view filters prefetches & filters.
        """

        return None

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
        view = self.get_related_view()
        return _get_url(view, self.context, kwargs=kwargs)

    def get_meta(self):
        """ Return the relationships "Meta" object

        This is the relationships top-level meta object & by
        default nothing except an empty object is returned.

        :spec:
            jsonapi.org/format/#document-resource-object-relationships
        """

        return {}

    def get_related_view(self):
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

    def get_serializer(self, *args, **kwargs):
        """ Return a serializer instance for the related field

        If a context isn't passed then use the existing one so
        the serializer is init'd with the request & what not.
        """

        try:
            kwargs['context'] = kwargs.pop('context', self.context)
            return import_string(self.serializer)(*args, **kwargs)
        except ImportError:
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

        try:
            rid, rtype = data['id'], data['type']
            if self.rtype != rtype:
                self.fail('rtype_conflict', given=rtype, rtype=self.rtype)
        except (KeyError, TypeError):
            rid = None
        return super().to_internal_value(rid)

    def to_representation(self, value):
        """ Override DRF PrimaryKeyRelatedField `to_representation` """

        rid = super().to_representation(value)
        return self.get_data(rid)


class ManyResourceRelatedField(ResourceRelatedField):
    """ JSON API related field for relationships

    This field can be used as a drop-in replacement for the
    DRF PrimaryKeyRelatedField with many=True.

    A factory is probaby a way better pattern & if this needs
    any additional tweaking at all then I'm going to remove it
    cause it's a pain-in-the-ass! The alternative is to just
    pass `many=True` cause way too much horrible shit is taking
    place to avoid that one param.
    """

    def __init__(self, **kwargs):

        del kwargs['_many_invoked']
        super().__init__(**kwargs)

    def __new__(cls, *args, **kwargs):

        kwargs['linkage'] = False
        kwargs['read_only'] = True

        if '_many_invoked' not in kwargs:
            kwargs['_many_invoked'] = True
            return cls.many_init(*args, **kwargs)
        return super().__new__(cls, *args, **kwargs)
