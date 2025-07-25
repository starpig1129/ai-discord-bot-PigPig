# MIT License
# Copyright (c) 2024 starpig1129

"""
This package contains the built-in tools for the bot.

By importing the modules here, we ensure that the @tool decorators are run
and the tools are registered in the central tool registry.
"""

import os
import importlib

# Get the directory of the current package
package_dir = os.path.dirname(__file__)

# Iterate over all files in the package directory
for filename in os.listdir(package_dir):
    # Check if the file is a Python module and not the __init__.py file itself
    if filename.endswith('.py') and filename != '__init__.py':
        # Form the module name
        module_name = f".{filename[:-3]}"
        # Import the module dynamically
        importlib.import_module(module_name, package=__package__)