from setuptools import setup, find_packages

with open('README.md', 'r') as f:
    long_description = f.read()

setup(
    name='raven-formats',
    version='0.1',
    author='nikita488',
    description='Tools to work with formats used by Raven Software in MUA/XML2 games',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/nikita488/raven-formats',
    packages=find_packages(),
    include_package_data=True,
    licence='MIT',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Utilities'
    ],
    entry_points={
        'console_scripts': [
            'xmlb=raven_formats.xmlb:main'
        ]
    }
)