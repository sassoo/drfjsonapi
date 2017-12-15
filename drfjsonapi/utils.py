"""
    drfjsonapi.utils
    ~~~~~~~~~~~~~~~~~

    Private & probably shady helper utilities
"""

from django.core.exceptions import ObjectDoesNotExist


def _get_relationship(model, field_name):
    """ Get the model(s) from a Django related field

    If it's a many relationship then it will have the `all()`
    method & if it's a OneToOne without a value it will raise
    ObjectDoesNotExist. If it does have a value or is a ForeigKey
    then just get the field. It will return None if not set.

    Because of all that, this handles ToMany's, ForeigKey's
    & OneToOne fields.
    """

    try:
        return getattr(model, field_name).all()
    except ObjectDoesNotExist:
        return None
    except AttributeError:
        return getattr(model, field_name)


def _to_set(obj):
    """ Given an object wrap it in a set """

    try:
        return set(obj)
    except TypeError:
        if obj is None:
            return set()
        return set((obj,))
