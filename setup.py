import os
from setuptools import setup

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "guts",
    version = "0.0.0",
    author = "Dan Tillberg",
    author_email = "dan@tillberg.us",
    description = ("Realtime bidirectional folder synchronization via modified git"),
    license = "ISC",
    keywords = "example documentation tutorial",
    url = "https://github.com/tillberg/guts",
    packages = ['guts'],
    long_description = read('README.md'),
    classifiers = [
        "Development Status :: 3 - Alpha",
        "Topic :: Utilities",
        "License :: OSI Approved :: ISC License",
    ],
    entry_points = {
        'console_scripts': [
            'guts = guts:main',
            'gut = guts:gut_proxy',
        ],
    }
)
