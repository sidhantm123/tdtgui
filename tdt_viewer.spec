# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for TDT Multi-Channel Viewer.

Build commands:
    Windows: pyinstaller tdt_viewer.spec
    macOS:   pyinstaller tdt_viewer.spec

The resulting executable will be in dist/TDT_Viewer/
"""

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all submodules for packages that need them
hiddenimports = [
    'scipy.signal',
    'scipy.fft',
    'scipy._lib.messagestream',
    'numpy',
    'pyqtgraph',
    'tdt',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
]

# Add scipy submodules
hiddenimports += collect_submodules('scipy')

# Data files
datas = []
datas += collect_data_files('pyqtgraph')

# Try to collect tdt data files if available
try:
    datas += collect_data_files('tdt')
except Exception:
    pass

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'IPython',
        'jupyter',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TDT_Viewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Set to True for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if sys.platform == 'win32' else 'assets/icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TDT_Viewer',
)

# macOS app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='TDT_Viewer.app',
        icon='assets/icon.icns',
        bundle_identifier='com.tdtviewer.app',
        info_plist={
            'CFBundleName': 'TDT Viewer',
            'CFBundleDisplayName': 'TDT Multi-Channel Viewer',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
            'NSRequiresAquaSystemAppearance': False,
        },
    )
