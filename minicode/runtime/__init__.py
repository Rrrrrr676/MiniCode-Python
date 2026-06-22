"""Agent runtime package.

The stable public entry point lives at :mod:`minicode.agent_loop`.  Keeping
this package initializer side-effect free lets lower-level runtime modules be
imported without eagerly importing the composition root.
"""
