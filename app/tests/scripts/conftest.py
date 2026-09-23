# SPDX-License-Identifier: Apache-2.0
"""Make the host scripts (app/scripts, app/boot) importable as modules."""

import os
import sys

APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for sub in ('scripts', 'boot'):
    path = os.path.join(APP, sub)
    if path not in sys.path:
        sys.path.insert(0, path)
