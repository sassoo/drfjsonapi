"""
    drfjsonapi.pagination
    ~~~~~~~~~~~~~~~~~~~~~~

    DRF custom pagination to assist with a JSONAPI spec
    compliant API.
"""

from rest_framework.pagination import LimitOffsetPagination as _LimitOffsetPagination
from rest_framework.utils.urls import remove_query_param, replace_query_param

from .exceptions import InvalidPageParam


class JsonApiPagination:
    """ Base pager for all JsonApiPagers """

    pass


class LimitOffsetPagination(JsonApiPagination, _LimitOffsetPagination):
    """ Override default LimitOffsetPagination to be JSON API compliant

    JSON API details
    ~~~~~~~~~~~~~~~~

    The JSON API spec reserves the `page` query parameter for
    pagination.

    This pager can be used to support the `page[limit]` &
    `page[offset]` query params for requesting pagination.

    The JSON API spec guidelines requires pagination links for
    the following four items: first, last, next, & prev. DRF
    already has next & previous links so this pager adds the
    first & last. Additionaly, the previous link is renamed
    to prev to conform with JSON API guidelines.

    Some helpful counters are included that could be use in
    a JSON API meta object, these include limit & offset.

    Implementation details
    ~~~~~~~~~~~~~~~~~~~~~~

    DRF already does a great job but instead of only ever
    ignoring any errors this pager will report back meaningful
    errors.

    Additionally, it creates a top-level pager key in the the
    response.data instead of all the other top-level keys that
    DRF would do. The pager automatically places meta related
    content in the pager['meta'] key & links related content
    in the pager['links'] key.
    """

    max_limit = float('inf')
    limit_query_param = 'page[limit]'
    offset_query_param = 'page[offset]'

    def get_first_link(self):
        """ Return the URL of the first paginated page """

        if not self.get_previous_link():
            return None

        return remove_query_param(
            self.request.build_absolute_uri(),
            self.offset_query_param
        )

    def get_last_link(self):
        """ Return the URL of the last paginated page """

        if not self.get_next_link():
            return None

        return replace_query_param(
            self.request.build_absolute_uri(),
            self.offset_query_param,
            self.count - self.limit,
        )

    def get_limit(self, request):
        """ Coerce, validate, & return the `page[limit]` query param """

        limit = request.query_params.get(
            self.limit_query_param,
            self.default_limit,
        )

        try:
            limit = int(limit)
            if limit < 0 or limit > self.max_limit:
                raise ValueError
        except TypeError:
            pass
        except ValueError:
            msg = 'The "%s" query param must be a positive number ' \
                  'greater than 0 but less than the max of %s' \
                  % (self.limit_query_param, self.max_limit)
            raise InvalidPageParam(msg)

        return limit

    def get_offset(self, request):
        """ Coerce, validate, & return the `page[offset]` query param """

        offset = request.query_params.get(self.offset_query_param, 0)
        try:
            offset = int(offset)
            if offset < 0:
                raise ValueError
        except ValueError:
            msg = 'The "%s" query param must be a positive number ' \
                  'greater than 0' % self.offset_query_param
            raise InvalidPageParam(msg)

        return offset

    def get_paginated_response(self, data):
        """ Add the additional paging links & counters

        Instead of polluting the top-level object like DRF would do
        create a pager top-level object with links & meta.
        """

        resp = super().get_paginated_response(data)
        resp.data['pager'] = {
            'links': {
                'first': self.get_first_link(),
                'last': self.get_last_link(),
                'next': resp.data.pop('next'),
                'prev': resp.data.pop('previous'),
            },
            'meta': {
                'limit': self.limit,
                'offset': self.offset,
                'total': resp.data.pop('count'),
            },
        }
        return resp
