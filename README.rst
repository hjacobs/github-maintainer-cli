=====================
GitHub Maintainer CLI
=====================

.. image:: https://img.shields.io/pypi/dw/github-maintainer.svg
   :target: https://pypi.python.org/pypi/github-maintainer/
   :alt: PyPI Downloads

.. image:: https://img.shields.io/pypi/v/github-maintainer.svg
   :target: https://pypi.python.org/pypi/github-maintainer/
   :alt: Latest PyPI version

.. image:: https://img.shields.io/pypi/l/github-maintainer.svg
   :target: https://pypi.python.org/pypi/github-maintainer/
   :alt: License

Command line tool to help you in the role of an Open Source project maintainer on GitHub.

* Reads ``MAINTAINERS`` file to find repositories you are responsible for
* Allows listing open issues and pull requests

Why?
====

One could argue that the GitHub "watch" feature (+ notifications) should be enough to get along,
but what if I want to watch many repositories but only maintain a few?

GitHub has no notion of a "project maintainer",
therefore we use the convention of putting a ``MAINTAINERS`` file in the root of each git repository.

Each person listed in the ``MAINTAINERS`` file is responsible for managing issues, pull requests and keeping code quality.

This tool should support you as a maintainer in doing so easily from the command line.

Usage
=====

.. code-block:: bash

    $ sudo pip3 install -U github-maintainer
    $ github-maintainer configure      # initial setup
    $ github-maintainer repositories   # list my repos
    $ github-maintainer issues         # list my issues
    $ github-maintainer pull-requests  # list my PRs
    $ github-maintainer patch 'myorg/.*' Dockerfile 'openjdk:8.*' openjdk:8-123  # replace patterns

Running Unit Tests
==================

.. code-block:: bash

    $ python3 setup.py test --cov-html=true

Releasing
=========

.. code-block:: bash

    $ ./release.sh <NEW-VERSION>
