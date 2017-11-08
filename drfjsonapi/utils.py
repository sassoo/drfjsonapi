"""
    drfjsonapi.utils
    ~~~~~~~~~~~~~~~~~

    Private & probably shady helper utilities
"""

from functools import reduce
from django.core.exceptions import ObjectDoesNotExist


def _dict_merge(master, new):
    """ Merge the new dict into the master dict recursively

    This is super naive & is really only tested to work with the
    the type of dict's generated from `_reduce_str_to_dict`.

    It can merge two dicts like:

        {'actor': {'movies': {}}}
        {'actor': {'salaries': {}}}

    into a single dict (master is mutated) that looks like:

        {'actor': {'movies': {}, 'salaries': {}}}
    """

    for key, val in master.items():
        if key in new:
            new[key] = _dict_merge(val, new[key])
    master.update(new)
    return master


def _get_related_field(model, field_name):
    """ Get the model(s) from a Django related field

    If it's a many relationship then it will have the
    `all()` method & if it's a OneToOne without a value
    it will raise ObjectDoesNotExist. If it does have a
    value or is a ForeigKey then just get the field. It
    will return None if not set.

    Because of all that, this handles ToMany's, ForeigKey's
    & OneToOne fields.
    """

    try:
        return getattr(model, field_name).all()
    except ObjectDoesNotExist:
        return None
    except AttributeError:
        return getattr(model, field_name)


def _reduce_str_to_dict(field, val=None, sep='__'):
    """ Given a django style field string return a dict

    This will turn something like 'actor__movies__venues' into
    a dict of:

        {'actor': {'movies': {'venues': None}}}
    """

    val = val or {}
    return reduce(lambda x, y: {y: x}, reversed(field.split(sep) + [val]))
