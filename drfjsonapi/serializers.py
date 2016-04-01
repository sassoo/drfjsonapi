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
from django.utils.functional import cached_property
from django.utils.module_loading import import_string
from rest_framework import exceptions
from rest_framework import serializers
from rest_framework.relations import ManyRelatedField


# pylint: disable=abstract-method
class JsonApiSerializer(serializers.Serializer):
    """ JSON API Serializer """

    @cached_property
    def related_fields(self):
        """ Return a dict of relationship fields """

        fields = {}
        for name, field in self.fields.items():
            if field.write_only:
                continue
            elif isinstance(field, ManyRelatedField):
                fields[name] = field.child_relation
            elif isinstance(field, ResourceRelatedField):
                fields[name] = field
        return fields

    @cached_property
    def related_includable(self):
        """ Cached property of `get_related_includable` """

        return self.get_related_includable()

    @cached_property
    def related_include(self):
        """ Cached property of `get_related_include` """

        return self.get_related_include()

    @cached_property
    def related_linkage(self):
        """ Cached property of `get_related_linkage` """

        return self.get_related_linkage()

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
        return {k: v for k, v in fields.items() if not v.write_only}

    def get_related_includable(self):
        """ Return a dict of readable fields that are includable """

        return {k: v for k, v in self.related_fields.items() if v.includable}

    def get_related_include(self):
        """ Return a dict of readable fields to include by default """

        return {k: v for k, v in self.related_fields.items() if v.include}

    def get_related_linkage(self):
        """ Return a dict of readable fields with data linkages """

        return {k: v for k, v in self.related_fields.items() if v.linkage}

    def get_related_serializer(self, field, **kwargs):
        """ Return a serializer instance for the related field """

        try:
            serializer = self.related_fields[field].serializer
            serializer = import_string(serializer)
            return serializer(context=self.context, **kwargs)
        except ImportError:
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

        data = super(JsonApiSerializer, self).to_representation(instance)

        self.sparse_filter(data)

        data['links'] = self.get_data_links(instance)
        data['meta'] = self.get_data_meta()
        data['type'] = self.get_rtype()
        return data


class JsonApiModelSerializer(JsonApiSerializer, serializers.ModelSerializer):
    """ JSON API ModelSerializer """
    pass
