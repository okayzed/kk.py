from distutils.core import setup

setup(
    name='KitchenSink',
    version='0.0.1',
    author='okay',
    author_email='okay.zed+kk@gmail.com',
    packages=['kitchen_sink' ],
    scripts=['bin/kk'],
    url='http://pypi.python.org/pypi/KitchenSink/',
    license='LICENSE.txt',
    description='Another pager .',
    long_description=open('README.md').read(),
    install_requires=[
    "urwid >= 1.0",
    "pygments",
    ],
    )

