gnenv
==

Goodnight Environment

## For new versions

```
python setup.py sdist bdist_wheel
twine check dist/*
twine upload --repository-url https://test.pypi.org/legacy/ dist/*
twine upload dist/*
```
