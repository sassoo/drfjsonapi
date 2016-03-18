"""
    drf_jsonapi.exceptions
    ~~~~~~~~~~~~~~~~~~~~~~

    DRF exceptions that are JSON API spec compliant.
"""

from rest_framework import exceptions


class ManyExceptions(exceptions.APIException):
    """ Exception that takes a list of other exceptions """

    def __init__(self, excs):
        super(ManyExceptions, self).__init__()
        self.excs = excs

    @property
    def status_code(self):
        """ Return an APIException compliant status_code attribute

        Per the JSON API spec errors could have different status
        codes & a generic one should be chosen in these conditions
        for the actual HTTP response code.
        """

        codes = [exc.status_code for exc in self.excs]
        same = all(code == codes[0] for code in codes)

        if not same and codes[0].startswith('4'):
            return 400
        elif not same and codes[0].startswith('5'):
            return 500
        else:
            return codes[0]


"""
    400 Bad Request
    ~~~~~~~~~~~~~~~
"""


class InvalidQueryParam(exceptions.APIException):
    """ The request has an invalid query parameter """

    default_detail = 'Your request had an invalid query parameter.'
    link = 'https://tools.ietf.org/html/rfc7231#section-6.5.1'
    status_code = 400
    title = 'Invalid or corrupt query parameter'


class InvalidFieldParam(InvalidQueryParam):
    """ The request has an invalid "field" query parameter """

    default_detail = 'Your request had an invalid "field" query parameter.'
    link = 'http://jsonapi.org/format/#fetching-sparse-fieldsets'
    source = {'parameter': 'field'}


class InvalidFilterParam(InvalidQueryParam):
    """ The request has an invalid "filter" query parameter """

    default_detail = 'Your request had an invalid "filter" query parameter.'
    link = 'http://jsonapi.org/format/#fetching-filtering'
    source = {'parameter': 'filter'}


class InvalidIncludeParam(InvalidQueryParam):
    """ The request has an invalid "include" query parameter """

    default_detail = 'Your request had an invalid "include" query parameter.'
    link = 'http://jsonapi.org/format/#fetching-includes'
    source = {'parameter': 'include'}


class InvalidPageParam(InvalidQueryParam):
    """ The request has an invalid "page" query parameter """

    default_detail = 'Your request had an invalid "page" query parameter.'
    link = 'http://jsonapi.org/format/#fetching-pagination'
    source = {'parameter': 'page'}


class InvalidSortParam(InvalidQueryParam):
    """ The request has an invalid "sort" query parameter """

    default_detail = 'Your request had an invalid "sort" query parameter.'
    link = 'http://jsonapi.org/format/#fetching-sorting'
    source = {'parameter': 'sort'}


"""
    404 Not Found
    ~~~~~~~~~~~~~
"""


class GenericNotFound(exceptions.APIException):
    """ Generic 404 error """

    link = 'https://tools.ietf.org/html/rfc7231#section-6.5.4'
    status_code = 404


class ResourceNotFound(GenericNotFound):
    """ The individual resource requested does not exist """

    default_detail = 'The endpoint requested processed your request ' \
                     'just fine but was unable to find the resource ' \
                     'requested. Did it get deleted?'
    title = 'Resource not found'


class RouteNotFound(GenericNotFound):
    """ The API endpoint requested does not exist """

    default_detail = 'The endpoint requested could not be found as ' \
                     'it seems no routes are even registered by that ' \
                     'URL. This is commonly a spelling error.'
    title = 'API endpoint not found'


"""
    405 Method Now Allowed
    ~~~~~~~~~~~~~~~~~~~~~~
"""


class MethodNotAllowed(exceptions.APIException):
    """ Custom 405 Method Now Allowed error for more info """

    default_detail = 'The "{method}" is not allowed at that endpoint. ' \
                     'Only "{allowed_methods}" methods are allowed for ' \
                     'that endpoint.'
    link = 'https://tools.ietf.org/html/rfc7231#section-6.5.5'
    status_code = 405
    title = 'HTTP method not allowed'

    def __init__(self, request, view, detail=None):
        """ Initialize the default message """

        if detail is None:
            detail = self.default_detail.format(
                allowed_methods=', '.join(view.allowed_methods),
                method=request.method,
            )
        super(MethodNotAllowed, self).__init__(detail)


"""
    406 Not Acceptable
    ~~~~~~~~~~~~~~~~~~
"""


class NotAcceptable(exceptions.APIException):
    """ The request requires a supported Accept header """

    default_detail = 'The endpoint requested does not support the mimetype ' \
                     'specified in your Accept header. You can use */* if ' \
                     'you want to use auto-negotation.'
    link = 'https://tools.ietf.org/html/rfc7231#section-6.5.6'
    status_code = 406
    title = 'Unacceptable response preference'


"""
    409 Conflict
    ~~~~~~~~~~~~
"""


class ConflictError(exceptions.APIException):
    """ The request could not be completed due to a conflict in state """

    default_detail = 'Your request had a generic resource conflict.'
    link = 'https://tools.ietf.org/html/rfc7231#section-6.5.8'
    status_code = 409
    title = 'Resource conflict error'


"""
    415 Unsupported Media Type
    ~~~~~~~~~~~~~~~~~~~~~~~~~~
"""


class UnsupportedMediaType(exceptions.APIException):
    """ The request requires a supported Content-Type header """

    default_detail = 'The endpoint requested & the HTTP method used ' \
                     'requires a valid Content-Type header. Unfortunately, ' \
                     'we couldn\'t find the header in your request or ' \
                     'the one provided is unsupported.'
    link = 'https://tools.ietf.org/html/rfc7231#section-6.5.13'
    status_code = 415
    title = 'Content-type header missing or unsupported'
