"""
    drfjsonapi.serializers
    ~~~~~~~~~~~~~~~~~~~~~~~

    DRF serializers to assist with a JSON API spec compliant API.

    Specifically, the JsonApiRenderer requires the use of the
    JsonApiSerializer
"""

from .exceptions import (
    FieldError,
    ManyExceptions,
    RelationshipError,
    ResourceError,
)
from .relations import ResourceRelatedField
from .utils import _get_resource_url
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string
from rest_framework import exceptions
from rest_framework import serializers
from rest_framework.relations import ManyRelatedField


# pylint: disable=abstract-method
class JsonApiSerializer(serializers.Serializer):
    """ JSON API Serializer """

    @property
    def related_fields(self):
        """ Return a list of relationship field names """

        names = []
        for name, field in self.fields.items():
            if isinstance(field, ManyRelatedField):
                field = field.child_relation
            if isinstance(field, ResourceRelatedField):
                names.append(name)
        return names

    def get_data_links(self, instance):
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

    def get_data_meta(self):
        """ Return the "Meta" object for an individual resource

        This should return a dict that is compliant with the
        document meta section of the JSON API spec. Specifically,
        the links section of an individual "Resource Object".

        :spec:
            jsonapi.org/format/#document-meta
        """

        return {}

    def get_default_includes(self):
        """ Return a list of related fields to include by default

        The serializers `Meta.default_includes` property is
        used to source the items.
        """

        # pylint: disable=no-member
        return [f for f in self.related_fields if f.include]

    def get_default_sorts(self):
        """ Return a list of fields to sort by default

        The serializers `Meta.default_sorts` property is
        used to source the items.
        """

        # pylint: disable=no-member
        return getattr(self.Meta, 'default_sorts', [])

    def get_fields_filterable(self):
        """ Return a dict of fields allowed to be filtered on

        By default the `Meta.fields_filterable` property is
        used to source the items.

        The key of each item is the string name of the field &
        the value is the `FilterField` object instance. Only
        readable fields will be returned for your safety.
        """

        readable = self.get_readable_fields()
        # pylint: disable=no-member
        fields = getattr(self.Meta, 'fields_filterable', {})
        return {k: v for k, v in fields.items() if k in readable}

    def get_fields_includable(self):
        """ Return a list of includable field names

        The serializers `Meta.fields_includable` property is
        used to source the items. If no fields_includable meta
        property is set then all readable related fields are
        eligable for inclusion.
        """

        readable = self.get_readable_fields()
        # pylint: disable=no-member
        fields = getattr(self.Meta, 'fields_includable', self.related_fields)
        return [field for field in fields if field in readable]

    def get_fields_sortable(self):
        """ Return a list of sortable field names

        The serializers `Meta.fields_sortable` property is
        used to source the items.
        """

        readable = self.get_readable_fields()
        # pylint: disable=no-member
        fields = getattr(self.Meta, 'fields_sortable', [])
        return [field for field in fields if field in readable]

    def get_readable_fields(self):
        """ Return `fields` but pruned to only readable fields

        A plain old dict is returned of field name & field as
        key/val just like `fields`.
        """

        return {f.field_name: f for f in self._readable_fields}

    def get_related_serializer(self, field_name, **kwargs):
        """ Return a serializer instance for the related field """

        try:
            # pylint: disable=no-member
            serializer = self.Meta.related_serializers[field_name]
            serializer = import_string(serializer)
            return serializer(context=self.context, **kwargs)
        except (AttributeError, KeyError, ImportError):
            return None

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
                        _exc = RelationshipError(error)
                    else:
                        _exc = FieldError(error)
                    _exc.source = {'pointer': '/%s' % field}
                    excs.append(_exc)
        raise ManyExceptions(excs)

    def sparse_filter(self, data):
        """ Trim fields based on the sparse fieldset request

        The JSON API spec uses the resource type (rtype) to
        qualify which fields should be returned.
        """

        try:
            sparse = self.context['request']._sparse_cache
        except (AttributeError, KeyError):
            sparse = {}

        for rtype, fields in sparse.items():
            if rtype == self.get_rtype():
                for key in data.keys():
                    if key not in fields:
                        del data[key]

    def to_internal_value(self, data):
        """ DRF override for error handling """

        try:
            return super(JsonApiSerializer, self).to_internal_value(data)
        except exceptions.ValidationError as exc:
            self.process_validation_errors(exc)

    def to_representation(self, instance):
        """ DRF override for consistent representation

        This should do only enough to support a common representation
        across different renderers & more importantly parsers. The
        format should be easily consumed back via a parser without
        all parsers having to be JSON API aware.

        Basically, include only what you'd like to have across
        ALL renderers & parsers.

        In this implementation a few additional keywords are
        reserved per JSON API like: `meta`, `links`, & `type`.
        Any instances used cannot have fields with those names.
        """

        print '1. trim all but sparse fields if present'
        print '2. trim all related not included & not related_linkage'
        print '3. pass include into the context'

        data = super(JsonApiSerializer, self).to_representation(instance)

        data['links'] = self.get_data_links(instance)
        data['meta'] = self.get_data_meta()
        data['type'] = self.get_rtype()
        return data


class JsonApiModelSerializer(JsonApiSerializer, serializers.ModelSerializer):
    """ JSON API ModelSerializer """
    pass
