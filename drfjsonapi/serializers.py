"""
    drfjsonapi.serializers
    ~~~~~~~~~~~~~~~~~~~~~~

    DRF serializers to assist with a JSON API spec compliant API.

    Specifically, the JsonApiRenderer requires the use of the
    JsonApiSerializer
"""

from django.core.exceptions import ImproperlyConfigured
from django.urls import NoReverseMatch, reverse
from django.utils.functional import cached_property
from rest_framework import exceptions
from rest_framework.relations import ManyRelatedField
from .exceptions import (
    FieldError,
    ManyExceptions,
    RelationshipError,
    ResourceError,
    RtypeConflict,
)
from .relations import JsonApiRelatedField


class IncludePerfMixin:
    """ JSON API include optimization Serializer mixin (optional) """

    def __init__(self, *args, **kwargs):
        """ Optimize & intelligently handle JSON API resources

        If a `data` kwarg is provided then it's assumed a modification is
        desired (create or update) & all relationship fields will resolve
        which may cause a database query.

        If a `data` kwarg is not provided then an `include` iterable is
        checked in the context passed of relationship fields that will
        resolve. Otherwise they are skipped as an optimization.
        """

        super().__init__(*args, **kwargs)

        if not kwargs.get('data'):
            include = self.context.get('include', ())
            for name in self._related_field_names:
                if name not in include:
                    self.fields[name].write_only = True


class JsonApiSerializerMixin:
    """ JSON API Serializer mixin """

    serializer_related_field = JsonApiRelatedField

    @cached_property
    def _related_field_names(self):
        """ Return related field names """

        return [
            name for name, field in self.fields.items()
            if isinstance(field, (JsonApiRelatedField, ManyRelatedField))
        ]

    @property
    def rtype(self) -> str:
        """ Return the string resource type as referenced by JSON API """

        try:
            return self.Meta.rtype
        except AttributeError:
            msg = '"%s" must have a `Meta.rtype` attribute representing ' \
                  'the JSON API resource type' % self.__class__.__name__
            raise ImproperlyConfigured(msg)

    def _to_representation_relationships(self, data) -> dict:
        """ Return the "Relationships Object" for a resource

        Relationships always get top-level links but if they have
        been included then the "Resource Linkage" is added to the
        object as well.

        :spec:
            jsonapi.org/format/#document-resource-object-relationships
        """

        relationships = {}
        for name in self._related_field_names:
            related_view = '%s-%s' % (self.rtype, name)
            related_view = related_view.replace('_', '-')
            relationships[name] = {
                'links': {
                    'related': reverse(related_view, args=(data['id'],))
                },
            }
            if name in data:
                relationships[name]['data'] = data.pop(name)
        return relationships

    def _process_validation_errors(self, exc):
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
                    if field in self._related_field_names:
                        excs.append(RelationshipError(field, error))
                        del exc.detail[field]

            # only field errors left now
            for field, errors in _flatten(exc.detail).items():
                for error in errors:
                    if field == 'non_field_errors':
                        excs.append(ResourceError(error))
                    else:
                        excs.append(FieldError(field, error))

        raise ManyExceptions(excs)

    def is_valid(self, **kwargs):  # pylint: disable=arguments-differ
        """ DRF override for error handling """

        try:
            return super().is_valid(**kwargs)
        except exceptions.ValidationError as exc:
            self._process_validation_errors(exc)

    def to_internal_value(self, data):
        """ DRF override for better error handling """

        if data['type'] != self.rtype:
            raise RtypeConflict(given=data['type'], rtype=self.rtype)
        return super().to_internal_value(data)

    def to_representation(self, instance):
        """ DRF override return an individual "Resource Object" object

        The renderer will later wrap it with the "Top Level" members.
        """

        data = super().to_representation(instance)

        try:
            links = {'self': reverse(self.rtype + '-detail', args=[instance.pk])}
        except (AttributeError, NoReverseMatch):
            links = {}

        return {
            'attributes': data,
            'links': links,
            'relationships': self._to_representation_relationships(data),
            'type': self.rtype,
            'id': str(data.pop('id')),
        }
