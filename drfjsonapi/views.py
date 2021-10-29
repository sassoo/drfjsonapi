"""
    drfjsonapi.views
    ~~~~~~~~~~~~~~~~~

    Custom views mostly for consistent exception handling
"""

import traceback

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.http import Http404
from django.urls import resolve, reverse
from django.utils.crypto import get_random_string
from rest_framework import exceptions
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .exceptions import (
    FieldError,
    InternalError,
    ManyExceptions,
    ResourceError,
    ResourceNotFound,
    RouteNotFound,
)
from .filters import JsonApiIncludeFilter
from .renderers import JsonApiRenderer
from .pagination import LimitOffsetPagination
from .parsers import JsonApiResourceParser


def _get_error(exc):
    """ Same order as error members documented in JSON API """

    return {
        'id': get_random_string(),
        'links': {'about': getattr(exc, 'link', '')},
        'status': str(exc.status_code),
        'code': getattr(exc, 'code', exc.__class__.__name__),
        'title': getattr(exc, 'title', str(exc)),
        'detail': getattr(exc, 'detail', str(exc)),
        'source': getattr(exc, 'source', {'pointer': ''}),
        'meta': getattr(exc, 'meta', {}),
    }


def _get_errors(response, exc):
    """ Set the root 'errors' key of the exception(s)

    The exception could be a ManyExceptions containing multiple
    APIExceptions or a single APIException. Either way JSON API
    requires an 'errors' root key with an array.
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
    """

    if isinstance(exc, Http404):
        exc = ResourceNotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied(str(exc))
    elif isinstance(exc, exceptions.ValidationError):
        excs = ManyExceptions([])
        for field, errors in exc.detail.items():
            for error in errors:
                try:
                    error = str(errors[error][0])
                except (KeyError, TypeError):
                    pass
                excs.excs.append(FieldError('/' + field, error))
        exc = excs
    elif isinstance(exc, ValidationError) and hasattr(exc, 'message_dict'):
        excs = ManyExceptions([])
        for field, errors in exc.message_dict.items():
            for error in errors:
                excs.excs.append(FieldError(field, error))
        exc = excs
    elif isinstance(exc, ValidationError):
        excs = ManyExceptions([])
        for error in exc.messages:
            excs.excs.append(ResourceError(error))
        exc = excs
    elif not isinstance(exc, exceptions.APIException):
        traceback.print_exc()  # print it
        exc = InternalError()

    response = exception_handler(exc, context)
    return _get_errors(response, exc)


@api_view()
def page_not_found(request):
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

    def get_included(self, serializer):
        """ Return the list of included resource objects """

        context = {'request': self.request, 'view': self}
        for backend in self.filter_backends:
            if issubclass(backend, JsonApiIncludeFilter):
                return backend().to_representation(serializer, context=context)
        return []

    def get_serializer_context(self):
        """ DRF override to inform serializers which related fields to include """

        context = super().get_serializer_context()
        context['include'] = getattr(self.request, 'jsonapi_include', ())
        return context

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
