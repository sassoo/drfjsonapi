"""
    drfjsonapi.filtersets
    ~~~~~~~~~~~~~~~~~~~~~

    Interface for handling JSON API query parameters like
    include & filter.

    A filterset is an API around all of the complexities
    of inclusions & filters including query generation &
    nested relationship handling.

    Rather than doing some naive like allowing every single
    relationship be included, every single field filtered
    upon, or even worse always using `.all()` on your
    relationship querysets like DRF wants to do - this
    interface gives you total flexbility.
"""

from django.db.models import Prefetch
from django.utils.module_loading import import_string


class BaseFilterSet:
    """ This should be subclassed by your custom FilterSet's """

    filterable_fields = {}
    includable_fields = {}
    includable_default_fields = ()
    related_filterset_fields = {}

    def __init__(self, context=None):
        """ Context will include the request & view """

        self.context = context or {}

    def remap_field(self, field):
        """ Must return field - XXX NOT WORKING """

        return field

    def is_filterable(self, field):
        """ Bool check to see if the field by name is filterable """

        return bool(self.get_filter_validator(field))

    def get_filter_validator(self, field):
        """ Return the fields filter validators """

        try:
            return self.filterable_fields[field]
        except (KeyError, TypeError):
            return None

    def get_filter_expression(self, query_param, field):
        """ Return any valid django filter expression for the field """

        return None

    def is_includable(self, field):
        """ Bool check to see if the field by name is includable """

        return bool(self.get_includable_serializer(field))

    def get_includable_default_fields(self):
        """ Return an array of fields to be included by default """

        return self.includable_default_fields

    def get_includable_prefetch(self, query_param, field):
        """ Return any valid Prefetch expression for the field """

        return Prefetch(query_param)

    def get_includable_serializer(self, field):
        """ Return the serializer instance for the included field """

        try:
            serializer_path = self.includable_fields[field]
            serializer_class = import_string(serializer_path)
            return serializer_class(context=self.context)
        except (ImportError, KeyError, TypeError):
            return None

    def get_related_filterset(self, field):
        """ Return the filterset instance for the related field

        This is necessary for validating filter & include params
        that span relationships.
        """

        try:
            filterset_path = self.related_filterset_fields[field]
            filterset_class = import_string(filterset_path)
            return filterset_class(context=self.context)
        except (ImportError, KeyError, TypeError):
            return None
