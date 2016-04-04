"""
    drfjsonapi.views
    ~~~~~~~~~~~~~~~~~

    Custom views mostly for consistent exception handling
"""

from .exceptions import (
    InvalidFieldParam,
    InvalidFilterParam,
    InvalidIncludeParam,
    InvalidPageParam,
    InvalidSortParam,
    ManyExceptions,
    MethodNotAllowed,
    NotAcceptable,
    ResourceNotFound,
    RouteNotFound,
    UnsupportedMediaType,
)
from .filters import *
from .pagination import JsonApiPagination
from .status_codes import status_codes
from .utils import _random_str
from django.core.urlresolvers import resolve, reverse
from django.http import Http404
from rest_framework import exceptions
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import exception_handler


@api_view()
def page_not_found(*args, **kwargs):  # pylint: disable=unused-argument
    """ Custom 404 endpoint not found view """

    raise RouteNotFound()


def generate_error_object(exc):
    """ Same order as error members documented in JSON API """

    return {
        'id': _random_str(),
        'links': {'about': getattr(exc, 'link', '')},
        'status': status_codes[exc.status_code],
        'code': getattr(exc, 'code', exc.__class__.__name__),
        'title': getattr(exc, 'title', ''),
        'detail': getattr(exc, 'detail', ''),
        'source': getattr(exc, 'source', {'pointer': ''}),
        'meta': getattr(exc, 'meta', {}),
    }


def jsonapi_exception_handler(exc, context):
    """ DRF custom exception handler for a JSON API backend

    The bulk of the work is substituting native DRF exceptions
    with our own that are more JSON API complete. Generally,
    they are much more informative errors as well.
    """

    import traceback
    traceback.print_exc(exc)
    raise exc
    response = exception_handler(exc, context)
    response.data = {'errors': []}

    if isinstance(exc, Http404):
        exc = ResourceNotFound()
    elif isinstance(exc, exceptions.MethodNotAllowed):
        exc = MethodNotAllowed(context['request'], context['view'])
    elif isinstance(exc, exceptions.NotAcceptable):
        exc = NotAcceptable()
    elif isinstance(exc, exceptions.NotAuthenticated):
        exc.title = 'Authentication is required'
    elif isinstance(exc, exceptions.ParseError):
        exc.title = 'Invalid or corrupt request body'
    elif isinstance(exc, exceptions.PermissionDenied):
        exc.title = 'Permission denied'
    elif isinstance(exc, exceptions.UnsupportedMediaType):
        exc = UnsupportedMediaType()

    if isinstance(exc, ManyExceptions):
        for _exc in exc.excs:
            response.data['errors'].append(generate_error_object(_exc))
    elif isinstance(exc, exceptions.APIException):
        response.data['errors'].append(generate_error_object(exc))

    return response


class JsonApiViewMixin(object):
    """ DRF view mixin for the JSON API

    This mixin should be used in any view that wants to
    follow the JSON API specification for managing resources.

    This mixin will enforce spec compliance where applicable
    at the early request processing stage. Currently, it's
    limited to determining if the query params used have been
    enabled on the view, via this modules filter_backends.
    """

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

    def get_serializer_context(self):
        """ Let the serializer know which related fields to include """

        context = super(JsonApiViewMixin, self).get_serializer_context()
        context['includes'] = getattr(self.request, '_includes', {}).keys()
        return context

    def initialize_request(self, request, *args, **kwargs):
        """ Perform some spec compliance checks as early as possible """

        filters = self.filter_backends
        request = super(JsonApiViewMixin, self).initialize_request(
            request, *args, **kwargs
        )

        for param in request.query_params.keys():
            if param.startswith('fields[') and SparseFilter not in filters:
                msg = '"field" query parameters are not supported'
                raise InvalidFieldParam(msg)
            elif param.startswith('filter[') and FieldFilter not in filters:
                msg = '"filter" query parameters are not supported'
                raise InvalidFilterParam(msg)
            elif param == 'include' and IncludeFilter not in filters:
                msg = '"include" query parameters are not supported'
                raise InvalidIncludeParam(msg)
            elif param.startswith('page['):
                if not isinstance(self.pagination_class, JsonApiPagination):
                    msg = '"page" query parameters are not supported'
                    raise InvalidPageParam(msg)
            elif param == 'sort' and OrderingFilter not in filters:
                msg = '"sort" query parameters are not supported'
                raise InvalidSortParam(msg)

        return request

    def render_related_detail_view(self, field, base_name):
        """ Render the related view of a single resource """

        name = '%s-detail' % base_name
        view = self._get_related_view(name, 'retrieve', kwargs={
            'pk': getattr(self.get_object(), field),
        })

        try:
            return view.retrieve(self.request)
        except Http404:
            return Response(None)

    def render_related_list_view(self, field, base_name):
        """ Render the related view of a resource collection """

        name = '%s-list' % base_name
        view = self._get_related_view(name, 'list')
        print 'XXX security leak without filter'
        view.queryset = getattr(self.get_object(), field).all()
        return view.list(self.request)
