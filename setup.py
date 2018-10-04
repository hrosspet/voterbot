from setuptools import setup

setup(
    name='voter',
    version=1,
    packages=['voter'],
    description="Voterbot",
    long_description="",
    url='https://github.com/hrosspet/voterbot',
    entry_points={
        'console_scripts': ['voterbot=voter.__main__:main'],
    },
    extras_require={
        'model': ["tensorflow", "keras", "numpy"]
    }
)
