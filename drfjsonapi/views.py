"""
    drfjsonapi.views
    ~~~~~~~~~~~~~~~~~

    Custom views mostly for consistent exception handling
"""

import traceback

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.urlresolvers import resolve, reverse
from django.utils.crypto import get_random_string
from django.http import Http404
from rest_framework import exceptions
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import exception_handler
from .exceptions import (
    FieldError,
    InternalError,
    InvalidFieldParam,
    InvalidFilterParam,
    InvalidIncludeParam,
    InvalidPageParam,
    InvalidSortParam,
    ManyExceptions,
    ResourceNotFound,
    RouteNotFound,
)
from .filters import (
    FieldFilter,
    OrderingFilter,
)
from .filtersets import JsonApiFilterSet
from .renderers import JsonApiRenderer
from .pagination import JsonApiPagination, LimitOffsetPagination
from .parsers import JsonApiResourceParser


def _get_error(exc):
    """ Same order as error members documented in JSON API """

    return {
        'id': get_random_string(),
        'links': {'about': getattr(exc, 'link', '')},
        'status': str(exc.status_code),
        'code': getattr(exc, 'code', exc.__class__.__name__),
        'title': getattr(exc, 'title', ''),
        'detail': getattr(exc, 'detail', str(exc)),
        'source': getattr(exc, 'source', {'pointer': ''}),
        'meta': getattr(exc, 'meta', {}),
    }


def _get_errors(response, exc):
    """ Set the root 'errors' key of the exception(s)

    The exception could be a ManyExceptions containing
    multiple APIExceptions or a single APIException. Either
    way JSON API requires an 'errors' root key with an array.
    """

    response.data = {'errors': []}
    for _exc in getattr(exc, 'excs', [exc]):
        response.data['errors'].append(_get_error(_exc))
    return response


def jsonapi_exception_handler(exc, context):
    """ DRF custom exception handler for a JSON API backend

    Turn the response payload into an array of "Error" objects.
    This will call the native DRF exception_handler which returns
    a response object that is further made JSON API compliant.

    This is done by calling _get_error() on each exception
    which will create a unique `id` for the error among
    other standard JSON API compliant key/vals.
    """

    if isinstance(exc, Http404):
        exc = ResourceNotFound()
    elif isinstance(exc, exceptions.NotAuthenticated):
        exc.title = 'Authentication is required'
    elif isinstance(exc, exceptions.ParseError):
        exc.title = 'Invalid or corrupt request body'
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied(str(exc))
        exc.title = 'Permission denied'
    elif isinstance(exc, exceptions.PermissionDenied):
        exc.title = 'Permission denied'
    elif isinstance(exc, exceptions.ValidationError):
        excs = ManyExceptions([])
        for field, errors in exc.detail.items():
            for error in errors:
                excs.excs.append(FieldError('/' + field, error))
        exc = excs
    elif isinstance(exc, ValidationError):
        excs = ManyExceptions([])
        for field, errors in exc.message_dict.items():
            for error in errors:
                excs.excs.append(FieldError('/' + field, error))
        exc = excs
    elif not isinstance(exc, exceptions.APIException):
        traceback.print_exc()  # print it
        exc = InternalError()

    response = exception_handler(exc, context)
    return _get_errors(response, exc)


@api_view()
def page_not_found():
    """ Custom 404 endpoint not found view """

    raise RouteNotFound()


class JsonApiViewMixin:
    """ DRF view mixin for the JSON API

    This mixin should be used in any view that wants to
    follow the JSON API specification for managing resources.

    This mixin will enforce spec compliance where applicable
    at the early request processing stage. Currently, it's
    limited to determining if the query params used have been
    enabled on the view, via this modules filter_backends.
    """

    filter_backends = (FieldFilter, OrderingFilter)
    pagination_class = LimitOffsetPagination
    parser_classes = (JsonApiResourceParser,)
    renderer_classes = (JsonApiRenderer,)

    def _get_related_view(self, view_name, action, kwargs=None):
        """ Return the related view instance & check global perms """

        view = resolve(reverse(view_name, kwargs=kwargs))
        view = view.func.cls(
            action=action,
            format_kwarg=self.format_kwarg,
            kwargs=kwargs,
            request=self.request,
        )

        view.check_permissions(self.request)
        return view

    def get_filterset(self):
        """ Return a filterset instance from the `filterset_class` property """

        try:
            return self.filterset_class(context=self.get_serializer_context())
        except AttributeError:
            filterable_fields = getattr(self, 'filterable_fields', {})
            return JsonApiFilterSet(context=self.get_serializer_context(),
                                    filterable_fields=filterable_fields)

    def initialize_request(self, request, *args, **kwargs):
        """ Perform some spec compliance checks as early as possible """

        filters = self.filter_backends
        request = super().initialize_request(
            request, *args, **kwargs
        )

        for param in request.query_params.keys():
            if param.startswith('fields['):
                msg = '"field" query parameters are not supported'
                raise InvalidFieldParam(msg)
            elif param.startswith('filter[') and FieldFilter not in filters:
                msg = '"filter" query parameters are not supported'
                raise InvalidFilterParam(msg)
            elif param == 'include':
                msg = '"include" query parameters are not supported'
                raise InvalidIncludeParam(msg)
            elif param.startswith('page['):
                if not issubclass(self.pagination_class, JsonApiPagination):
                    msg = '"page" query parameters are not supported'
                    raise InvalidPageParam(msg)
            elif param == 'sort' and OrderingFilter not in filters:
                msg = '"sort" query parameters are not supported'
                raise InvalidSortParam(msg)

        return request

    def render_related_view(self, field, view_name):
        """ Render the related view of a single resource

        NOTE: If it's a OneToOneField a DoesNotExist exception
              is thrown.
        """

        try:
            view = self._get_related_view(view_name, 'retrieve', kwargs={
                'pk': getattr(self.get_object(), field),
            })
            return view.retrieve(self.request)
        except (Http404, ObjectDoesNotExist):
            return Response(None)

    def render_related_list_view(self, field, view_name):
        """ Render the related view of a resource collection """

        view = self._get_related_view(view_name, 'list')
        view.queryset = getattr(self.get_object(), field).all()
        return view.list(self.request)
