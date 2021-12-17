
from setuptools import setup, find_packages

setup(
    name='bitahoy_sdk',
    #version="0.0.1-dev",
    description='',
    url='https://bitahoy.com',
    maintainer='Bitahoy',
    maintainer_email='contact@bitahoy.com',
    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'Programming Language :: Python :: 3',
    ],
    keywords='',
    packages=find_packages(),
    package_data={'bitahoy_sdk': ['data/*.txt']},
    scripts=[],
    include_package_data=True,
    install_requires=[
        "websockets",
        "dpkt",
    ],
)