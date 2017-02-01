"""
    drfjsonapi.decorators
    ~~~~~~~~~~~~~~~~~~~~~~

    Custom decorators mostly for specialized views
"""

from rest_framework.decorators import detail_route


def related_route(*args, **kwargs):
    """ Convenience decorator to support JSON API related resource link

    Instead of using a DRF detail_route decorator when constructing
    views that would resolve "Related Resource Links" according
    to the JSON API spec, you should use this decorator.

    It simply wraps the detail_route but skips the processing
    of filter_backends on the primary data since all query
    params provided are for the RELATED data & not the primary
    data.

    For example, `/actors/1/movies?sort=title` would ensure
    the sort query param would be processed on the movies
    resource & NOT the actors resource.

    :spec:
        jsonapi.org/format/#document-resource-object-related-resource-links
    """

    kwargs['filter_backends'] = kwargs.pop('filter_backends', ())
    return detail_route(*args, **kwargs)


def relationship_route(*args, **kwargs):
    """ Convenience decorator to support a JSON API relationship link

    Instead of using a DRF detail_route decorator when constructing
    views that would resolve "Relationship Links" according
    to the JSON API spec, you should use this decorator.

    :spec:
        jsonapi.org/format/#fetching-relationships
    """

    kwargs['filter_backends'] = kwargs.pop('filter_backends', ())
    kwargs['url_path'] = 'relationships/%s' % kwargs.pop('relation')
    return detail_route(*args, **kwargs)
