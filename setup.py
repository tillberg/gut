import os
from setuptools import setup

setup(
    name = "gut",
    version = "0.2.3",
    author = "Dan Tillberg",
    author_email = "dan@tillberg.us",
    description = ("Realtime bidirectional folder synchronization via modified git"),
    license = "ISC",
    keywords = "",
    url = "https://github.com/tillberg/gut",
    packages = ['gut'],
    install_requires=[
        "asyncssh>=1.2.0",
        "pycrypto>=2.6.1",
    ],
    classifiers = [
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "License :: OSI Approved :: ISC License (ISCL)",
    ],
    entry_points = {
        'console_scripts': [
            'gut = gut.shell:main',
        ],
    }
)
