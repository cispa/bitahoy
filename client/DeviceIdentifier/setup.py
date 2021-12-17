from setuptools import setup, find_packages

setup(
    name='device_identifier',
    version="0.0.1-dev",
    description='Device Identification in local networks',
    url='https://bitahoy.com',
    maintainer='Bitahoy',
    maintainer_email='contact@bitahoy.com',
    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'Programming Language :: Python :: 3',
        'Natural Language :: English',

    ],
    keywords='',
    packages=find_packages(),
    scripts=[],
    include_package_data=True,
    install_requires=[
        "zeroconf==0.31.0",
        "xmltodict==0.12.0",
        "ssdp",
        "requests",
        "aiohttp"
    ],
)