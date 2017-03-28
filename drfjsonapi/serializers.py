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
    RtypeConflict,
)
from .relations import ResourceRelatedField
from .utils import _get_resource_url


class IncludeMixin:
    """ Helpers for handling the include query param

    This supports maximum flexibility by relying on the
    relationship fields for included related directives
    so they can be encapsulated & reused while also
    allowing serializers to override if needed.

    The FilterBackends never know anything about the
    underlying relationship fields. Everything is
    proxied through this simple serializer mixin.
    """

    def get_includables(self):
        """ Return includable related field names """

        return [k for k, v in self.related_fields.items() if v.includable]

    def get_default_includables(self):
        """ Return the default related field names to include

        This is only used if the requestor did not explicitly
        request includes per the JSON API spec.
        """

        return [k for k, v in self.related_fields.items() if v.include]

    def get_related_queryset(self, field):
        """ Get the optional filtered queryset for the relationship """

        try:
            related_field = self.related_fields[field]
            return related_field.get_filtered_queryset()
        except (AttributeError, KeyError):
            return None

    def get_related_serializer(self, field):
        """ Return the default related field names to include

        This is only used if the requestor did not explicitly
        request includes per the JSON API spec.
        """

        try:
            related_field = self.related_fields[field]
            return related_field.get_serializer(context=self.context)
        except (AttributeError, KeyError):
            return None


# pylint: disable=abstract-method
class JsonApiSerializer(IncludeMixin, serializers.Serializer):
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

        includes = self.context.get('includes', {})
        relationships = {}
        for key, field in self.related_fields.items():
            relationships[key] = {
                'links': field.get_links(data['id']),
                'meta': field.get_meta(),
            }
            if key in includes or field.linkage:
                relationships[key].update({'data': data.pop(key)})
        return relationships

    def get_rtype(self):
        """ Return the string resource type as referenced by JSON API """

        meta = getattr(self, 'Meta', None)
        rtype = getattr(meta, 'rtype', None)
        if not rtype:
            msg = '"%s" must either have a `Meta.rtype` attribute ' \
                  'or override `get_rtype()`' % self.__class__.__name__
            raise ImproperlyConfigured(msg)
        return rtype

    def is_valid(self, **kwargs):
        """ DRF override for error handling """

        try:
            return super().is_valid(**kwargs)
        except exceptions.ValidationError as exc:
            self.process_validation_errors(exc)

    def process_validation_errors(self, exc):
        """ This should be called when handling serializer exceptions

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

        def _flatten(init, lkey=''):
            """ Recursively flatten embedded data types

            For embedded field types like a JSONField go through
            & convert the error key to a '/' separated string
            flattening them into a single dict.

            This allows for proper pointers in the error object
            """

            ret = {}
            for rkey, val in init.items():
                key = lkey + rkey
                if isinstance(val, dict):
                    ret.update(_flatten(val, key + '/'))
                else:
                    ret[key] = val
            return ret

        excs = []
        if isinstance(exc.detail, list):
            for error in exc.detail:
                excs.append(ResourceError(error))
        else:
            # prune the dict of all related field errors
            for field in list(exc.detail):
                for error in exc.detail[field]:
                    if field in self.related_fields:
                        excs.append(RelationshipError(field, error))
                        del exc.detail[field]

            # only field errors left now
            for field, errors in _flatten(exc.detail).items():
                for error in errors:
                    excs.append(FieldError(field, error))

        raise ManyExceptions(excs)

    def to_internal_value(self, data):
        """ DRF override for error handling

        Per the spec, first ensure the resource type provided
        matches that which is expected by this serializer.
        """

        if data['type'] != self.get_rtype():
            raise RtypeConflict(given=data['type'], rtype=self.get_rtype())

        try:
            return super().to_internal_value(data)
        except exceptions.ValidationError as exc:
            self.process_validation_errors(exc)

    def to_representation_sparse(self):
        """ Trim fields based on the sparse fields requested

        The JSON API spec uses the resource type (rtype) to
        qualify which fields should be returned.
        """

        try:
            sparse = self.context['sparse']
            fields = sparse[self.get_rtype()]
        except (AttributeError, KeyError):
            return

        for key in self.fields.keys():
            if key not in fields:
                del self.fields[key]

    def to_representation(self, instance):
        """ DRF override return an individual "Resource Object" object

        This should return a dict that is compliant with the
        "Resource Object" section of the JSON API spec. It
        will later be wrapped by the "Top Level" members.

        :spec:
            jsonapi.org/format/#document-resource-objects
        """

        self.to_representation_sparse()
        data = super().to_representation(instance)

        return {
            'attributes': data,
            'links': self.get_links(instance),
            'meta': self.get_meta(),
            'relationships': self.get_relationships(data=data),
            'type': self.get_rtype(),
            'id': data.pop('id'),
        }

    def validate_embedded(self, data, fields):
        """ Validate embedded lists helper method

        This is like DRF's `validate()` except it takes a tuple
        of tuples in the following format:

            (field_name, serializer_class)

        The fields values will be iterated & validated individually
        using the provided serializer. It will then construct
        proper ValidationError's so the JSON pointers reference the
        list index value where the error occurred.

        This is mostly useful for embedded objects where the django
        field is a JSONField.
        """

        errors = {}

        for name, serializer_class in fields:
            value = data.get(name, [])  # empty if PATCH

            for idx, data_item in enumerate(value):
                serializer = serializer_class(data=data_item)
                if not serializer.is_valid():
                    for item_field, error in serializer.errors.items():
                        errors['%s/%s/%s' % (name, idx, item_field)] = error

        if errors:
            raise serializers.ValidationError(errors)


class JsonApiModelSerializer(JsonApiSerializer, serializers.ModelSerializer):
    """ JSON API ModelSerializer """

    serializer_related_field = ResourceRelatedField


class PolymorphicSerializer(JsonApiSerializer):
    """ A very basic READ-ONLY Polymorphic serializer

    To use this each instance, typically a Django model,
    must have a designated field with a value that can be
    relied upon for distinguishing which serializer to use.

    The instance field is specified by a `polymorphic_instance_field`
    property on the Meta object:

        ```
        class Meta:
            polymorphic_instance_field = 'species'
            polymorphic_serializers = {
                'cat': CatSerializer,
                'dog': DogSerializer,
            }
        ```

    The `polymorphic_serializers` property is a dict of
    all the serializers that may be backing the instances.
    """

    def __init__(self, *args, **kwargs):
        """ Ensure the required properties are present """

        super().__init__(*args, **kwargs)
        instance_field = self.get_polymorphic_instance_field()
        _serializers = self.get_polymorphic_serializers()

        if not instance_field:
            msg = 'Using "%s" requires a "polymorphic_instance_field" ' \
                  'property on the Meta object'
            raise ImproperlyConfigured(msg % self.__class__.__name__)

        if not _serializers or not isinstance(_serializers, dict):
            msg = 'Using "%s" requires a "polymorphic_serializers" ' \
                  'field which must be a dict on the Meta object'
            raise ImproperlyConfigured(msg % self.__class__.__name__)

    def get_polymorphic_instance_field(self):
        """ Return the string instance field name """

        meta = getattr(self, 'Meta', None)
        return getattr(meta, 'polymorphic_instance_field', None)

    def get_polymorphic_serializers(self):
        """ Initialize all the backing serializers & return them """

        meta = getattr(self, 'Meta', None)
        return getattr(meta, 'polymorphic_serializers', {})

    def get_polymorphic_serializer(self, instance):
        """ Given an instance find the right serializer """

        instance_field = self.get_polymorphic_instance_field()
        instance_value = getattr(instance, instance_field)
        try:
            serializer = self.get_polymorphic_serializers()[instance_value]
            return serializer(context=self.context)
        except KeyError:
            return None

    def to_representation(self, instance):
        """ DRF override, use the instance_field on the instance """

        serializer = self.get_polymorphic_serializer(instance)
        return serializer.to_representation(instance)
