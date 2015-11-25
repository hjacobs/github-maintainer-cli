=====================
GitHub Maintainer CLI
=====================

Command line tool to help you in the role of an Open Source project maintainer on GitHub.

* Reads ``MAINTAINERS`` file to find repos you are responsible for
* Allows listing open issues and pull requests

Why?
====

One could argue that the GitHub "watch" feature (+ notifications) should be enough to get along,
but what if I want to watch many repositories but only maintain a few?

GitHub has no notion of a "project maintainer",
therefore we use the convention of putting a ``MAINTAINERS`` file in the root of each git repository.

Each person listed in the ``MAINTAINERS`` file is responsible for managing issues, pull requests and keeping code quality.

This tool should support you as a maintainer in doing so easily from the command line.

