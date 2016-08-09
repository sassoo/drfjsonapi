"""
    drfjsonapi.serializers
    ~~~~~~~~~~~~~~~~~~~~~~~

    DRF serializers to assist with a JSON API spec compliant API.

    Specifically, the JsonApiRenderer requires the use of the
    JsonApiSerializer
"""

from django.core.exceptions import ImproperlyConfigured
from rest_framework import exceptions
from rest_framework import serializers
from rest_framework.relations import ManyRelatedField
from .exceptions import (
    FieldError,
    ManyExceptions,
    RelationshipError,
    ResourceError,
)
from .relations import ResourceRelatedField
from .utils import _get_resource_url


# pylint: disable=abstract-method
class JsonApiSerializer(serializers.Serializer):
    """ JSON API Serializer """

    @property
    def related_fields(self):
        """ Return `self.fields` but limited to relationship fields """

        fields = {}
        for name, field in self.fields.items():
            if field.write_only:
                continue
            elif isinstance(field, ManyRelatedField):
                fields[name] = field.child_relation
            elif isinstance(field, ResourceRelatedField):
                fields[name] = field
        return fields

    def get_filterable_fields(self):
        """ Return a dict of fields allowed to be filtered on

        By default the `Meta.filterable_fields` property is
        used to source the items.

        The key of each item is the string name of the field &
        the value is the `FilterField` object instance. Only
        readable fields will be returned for your safety.
        """

        # pylint: disable=no-member
        fields = getattr(self.Meta, 'filterable_fields', {})
        return {
            k: v for k, v in fields.items()
            if not self.fields[k].write_only
        }

    def get_links(self, instance):
        """ Return the "Links" object for an individual resource

        This should return a dict that is compliant with the
        document links section of the JSON API spec. Specifically,
        the links section of an individual "Resource Object".

        :spec:
            jsonapi.org/format/#document-links
        """

        rtype = self.get_rtype()
        resource_url = _get_resource_url(rtype, instance.id, self.context)
        return {'self': resource_url}

    def get_meta(self):
        """ Return the "Meta" object for an individual resource

        This should return a dict that is compliant with the
        document meta section of the JSON API spec. Specifically,
        the links section of an individual "Resource Object".

        :spec:
            jsonapi.org/format/#document-meta
        """

        return {}

    def get_relationships(self, data):
        """ Return the "Relationships Object" for a resource

        This should return a dict that is compliant with the
        "Relationships Object" section of the JSON API spec.
        Specifically, the contents of the top level `relationships`
        member of an individual resource boject.

        Relationships always get top-level links & meta objects
        but if they have been included or require "Linkage" then
        the "Resource Linkage" is added to the object as well.

        Often to-one relationships will have linkage=True while
        to-many's won't since there could be alot of them.

        :spec:
            jsonapi.org/format/#document-resource-object-relationships
        """

        relationships = {}
        for key, field in self.related_fields.items():
            relationships[key] = {
                'links': field.get_links(data['id']),
                'meta': field.get_meta(),
            }

            if field.linkage or key in self.context['includes']:
                relationships[key]['data'] = data.pop(key)
        return relationships

    def get_rtype(self):
        """ Return the string resource type as referenced by JSON API """

        try:
            return getattr(self, 'Meta').rtype
        except AttributeError:
            msg = '"%s" should either include a `Meta.rtype` attribute, ' \
                  'or override `get_rtype()`' % self.__class__.__name__
            raise ImproperlyConfigured(msg)

    def process_validation_errors(self, exc):
        """ This should be called by `to_internal_value`

        Turn each DRF ValidationError error message in the
        `detail` property into an individual drfjsonapi
        ValidationError object. We want one error message
        per object.

        The JSON API spec has a `source` member that follows
        the JSON Pointer guidelines of RFC 6901 which points
        to a path in the payload representing the field
        responsible for the error.

        The renderer will then properly construct the source
        path. We do this so the source is meaningful across
        different renderers.
        """

        excs = []
        if isinstance(exc.detail, list):
            for error in exc.detail:
                excs.append(ResourceError(error))
        else:
            for field, errors in exc.detail.items():
                for error in errors:
                    if field in self.related_fields:
                        excs.append(RelationshipError(error))
                    else:
                        excs.append(FieldError(error))
                    excs[-1].source = {'pointer': '/%s' % field}
        raise ManyExceptions(excs)

    def to_internal_value(self, data):
        """ DRF override for error handling """

        try:
            return super(JsonApiSerializer, self).to_internal_value(data)
        except exceptions.ValidationError as exc:
            self.process_validation_errors(exc)

    def to_representation_sparse(self):
        """ Trim fields based on the sparse fields requested

        The JSON API spec uses the resource type (rtype) to
        qualify which fields should be returned.
        """

        try:
            sparse = self.context['request']._sparse_cache
            fields = sparse[self.get_rtype()]
        except (AttributeError, KeyError):
            return

        for key in self.fields.keys():
            if key not in fields:
                del self.fields[key]

    def to_representation(self, instance):
        """ Return an individual "Resource Object" object

        This should return a dict that is compliant with the
        "Resource Object" section of the JSON API spec. It
        will later be wrapped by the "Top Level" members.

        :spec:
            jsonapi.org/format/#document-resource-objects
        """

        self.to_representation_sparse()

        print 'related query still occurs even if linkage=False included'
        data = super(JsonApiSerializer, self).to_representation(instance)
        return {
            'attributes': data,
            'links': self.get_links(instance),
            'meta': self.get_meta(),
            'relationships': self.get_relationships(data),
            'type': self.get_rtype(),
            'id': data.pop('id'),
        }


class JsonApiModelSerializer(JsonApiSerializer, serializers.ModelSerializer):
    """ JSON API ModelSerializer """
    pass
