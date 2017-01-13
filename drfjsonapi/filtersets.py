"""
    drfjsonapi.filtersets
    ~~~~~~~~~~~~~~~~~~~~~

    XXX
"""

from django.db.models import Prefetch
from django.utils.module_loading import import_string


class BaseFilterSet:
    """
    HOW TO LINK FILTERSETS?!?!?!?
    # Filters
    #
    # [SERIALIZER] get the FilterValidator for the field
    # [FILTER BE] validate it
    # [SERIALIZER] get the filter expression for the field
    # [RELATED] if not found serializer will get it from relationship
    # [FILTER BE] update queryset with filters

    # Includes
    #
    # [FILTER_BE -> FILTERSET] call remap_field (remap qp)
    # [FILTER_BE -> FILTERSET] check if the field is includable
    # [FILTER_BE -> FILTERSET] get the include prefetch for the field
    # [FILTER_BE] update queryset with prefetchers
    """

    filterable_fields = {}
    includable_fields = {}
    includable_default_fields = ()
    related_filterset_fields = {}

    def __init__(self, context=None):
        """ XXX """

        self.context = context or {}

    def remap_field(self, field):
        """ Must return field """

        return field

    def is_filterable(self, field):
        """ XXX """

        return bool(self.get_filter_validator(field))

    def get_filter_validator(self, field):
        """ XXX """

        try:
            return self.filterable_fields[field]
        except (KeyError, TypeError):
            return None

    def get_filter_expression(self, query_param, field):
        """ XXX """

        return None

    def is_includable(self, field):
        """ XXX """

        return bool(self.get_includable_serializer(field))

    def get_includable_default_fields(self):
        """ XXX """

        return self.includable_default_fields

    def get_includable_prefetch(self, query_param, field):
        """ XXX """

        return Prefetch(query_param)

    def get_includable_serializer(self, field):
        """ XXX """

        try:
            serializer_path = self.includable_fields[field]
            serializer_class = import_string(serializer_path)
            return serializer_class(context=self.context)
        except (ImportError, KeyError, TypeError):
            return None

    def get_related_filterset(self, field):
        """ XXX """

        try:
            filterset_path = self.related_filterset_fields[field]
            filterset_class = import_string(filterset_path)
            return filterset_class(context=self.context)
        except (ImportError, KeyError, TypeError):
            return None
