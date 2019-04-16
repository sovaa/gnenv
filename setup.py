#!/usr/bin/env python

from setuptools import setup, find_packages

version = '0.1.3'

setup(
    name='gnenv',
    version=version,
    description="",
    long_description="""Goodnight Environment""",
    long_description_content_type='text/x-rst',
    classifiers=[],
    keywords='environment',
    author='Oscar Eriksson',
    author_email='oscar.eriks@gmail.com',
    url='',
    license='LICENSE.txt',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'strict-rfc3339==0.7',  # parsing dates
    ])
