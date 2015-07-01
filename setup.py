import os
from setuptools import setup

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "gut",
    version = "0.1.0",
    author = "Dan Tillberg",
    author_email = "dan@tillberg.us",
    description = ("Realtime bidirectional folder synchronization via modified git"),
    license = "ISC",
    keywords = "",
    url = "https://github.com/tillberg/gut",
    packages = ['gut'],
    long_description = read('README.md'),
    classifiers = [
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "License :: OSI Approved :: ISC License (ISCL)",
    ],
    entry_points = {
        'console_scripts': [
            'gut = gut.gut:main',
        ],
    }
)
