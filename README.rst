drfjsonapi
======================================

|build-status-image| |pypi-version|

Overview
--------

JSON API reference implementation for Django Rest Framework

This is an extremely thorough implementation of the JSON API 1.0 specification
for the Django Rest Framework. It has strict error handling of non-compliant
clients & follows all of the MUST's of the spec (or will soon where missing).

Known incomplete JSON API spec features/guidelines are:

-  Error object pointers
-  "Relationship Links"

Error object pointers isn't very great currently. It handles field-level,
resource-level, & relationship "pointer" construction just fine but I
don't think it will handle any sort of complex nested field errors. The
pointer may not be accurate. I'll have to test & figure out a way to do
that properly with DRF & it's native ValidationError field names.

This matters when you look at RFC 6901. We may need something more robust
here as an additional DRF plugin that drfjsonapi requires.


Relationship links are the "self" member of the links object for relationships.
Currently, ember doesn't support relationship modificiation for that endpoint
so I have no incentive yet to write it. Having said that, some abstractions
have already been written in this library to make the transition easy in the
future.

Aside from those known limitations this library is REALLY complete. A TON of
focus & attention was spent on meaningful errors & good exception handling.
Much more to come on that front as I'm aware needs to be more thorough but
those enhancements will come without needing to worry about the JSON API spec.

A breakdown of notable features currently implemented that you'd want in any
JSON API server implementation are:

-  ``filter`` query params (spanning relationships)
-  ``include`` query params (spanning relationships)
-  ``page`` query params
-  ``sort`` query params
-  related resource links
-  ridiculously easy to follow code
-  comprehensive error handling (parsers, serializers, views, etc)
-  error coalescing
-  hooks for almost every part of the JSON API processing pipeline
-  good quality code comments

Requirements
------------

-  Python (2.7, 3.3, 3.4)
-  Django (1.6, 1.7, 1.8)
-  Django REST Framework (2.4, 3.0, 3.1)

Installation
------------

Install using ``pip``\ …

.. code:: bash

    $ pip install drfjsonapi

Example
-------

TODO: Write example.

Testing
-------

Install testing requirements.

.. code:: bash

    $ pip install -r requirements.txt

Run with runtests.

.. code:: bash

    $ ./runtests.py

You can also use the excellent `tox`_ testing tool to run the tests
against all supported versions of Python and Django. Install tox
globally, and then simply run:

.. code:: bash

    $ tox

Documentation
-------------

To build the documentation, you’ll need to install ``mkdocs``.

.. code:: bash

    $ pip install mkdocs

To preview the documentation:

.. code:: bash

    $ mkdocs serve
    Running at: http://127.0.0.1:8000/

To build the documentation:

.. code:: bash

    $ mkdocs build

.. _tox: http://tox.readthedocs.org/en/latest/

.. |build-status-image| image:: https://secure.travis-ci.org/sassoo/drfjsonapi.svg?branch=master
   :target: http://travis-ci.org/sassoo/drfjsonapi?branch=master
.. |pypi-version| image:: https://img.shields.io/pypi/v/drfjsonapi.svg
   :target: https://pypi.python.org/pypi/drfjsonapi
