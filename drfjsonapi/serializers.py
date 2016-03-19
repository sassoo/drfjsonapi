"""
    drfjsonapi.serializers
    ~~~~~~~~~~~~~~~~~~~~~~~

    DRF serializers to assist with a JSON API spec compliant API.

    Specifically, the JsonApiRenderer requires the use of the
    JsonApiSerializer
"""

from .relations import ResourceRelatedField
from .utils import _get_resource_url
from django.core.exceptions import ImproperlyConfigured
from django.utils.functional import cached_property
from django.utils.module_loading import import_string
from rest_framework import serializers
from rest_framework.relations import ManyRelatedField


# pylint: disable=abstract-method
class JsonApiSerializer(serializers.Serializer):
    """ JSON API Serializer """

    @cached_property
    def related_field_names(self):
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

    def get_filter_fields(self):
        """ Return a dict of fields allowed to be filtered on

        By default the `Meta.filter_fields` property is used to
        source the items.

        The key of each item is the string name of the field &
        the value is the `FilterField` object instance. Only
        readable fields will be returned for your safety.
        """

        readable = self.get_readable_fields()
        # pylint: disable=no-member
        filter_fields = getattr(self.Meta, 'filter_fields', {})
        return {k: v for k, v in filter_fields.items() if k in readable}

    def get_inclusion_field_names(self):
        """ Return a list of inclusionable field names

        The serializers `Meta.inclusion_fields` object contains the
        list of inclusionable fields.

        Just in case some bonehead removes the field from the
        serializer or sets it write_only & forgets to remove it
        from the `Meta.inclusion_fields` property this will
        automatically prune them.

        NOTE: if no inclusion_fields meta property is set
              then all readable related fields are eligable
              for inclusion

        :returns:
            list of string field names
        """

        readable = self.get_readable_fields()
        meta = getattr(self, 'Meta')
        names = getattr(meta, 'inclusion_fields', self.related_field_names)
        return [name for name in names if name in readable]

    def get_readable_fields(self):
        """ Return `fields` but pruned to only readable fields

        A plain old dict is returned of field name & field as
        key/val just like `fields`.
        """

        return {f.field_name: f for f in self._readable_fields}

    def get_related_queryset(self, field_name):
        """ Return a queryset instance for the related field """

        try:
            meta = getattr(self, 'Meta')
            return meta.related_querysets[field_name]
        except (AttributeError, KeyError):
            return None

    def get_related_serializer(self, field_name, **kwargs):
        """ Return a serializer instance for the related field """

        try:
            meta = getattr(self, 'Meta')
            serializer = meta.related_serializers[field_name]
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

    def sparse_filter(self, data):
        """ Trim fields based on the sparse fieldset request """

        sparse_cache = getattr(self.context['request'], '_sparse_cache', {})
        for rtype, fields in sparse_cache.items():
            # always required
            fields += ['id', 'type']

            if rtype == self.get_rtype():
                for key in data.keys():
                    if key not in fields:
                        del data[key]

    def to_internal_value(self, data):
        """ DRF override for extra helper type stuff

        The meta `create_only_fields` list contains field names
        which can only be set during create & are not allowed to
        be mutated after.
        """

        meta = getattr(self, 'Meta')
        for field in getattr(meta, 'create_only_fields', ()):
            if self.instance and field in data:
                del data[field]
        return super(JsonApiSerializer, self).to_internal_value(data)

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
