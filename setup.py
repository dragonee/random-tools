from setuptools import setup, find_packages

setup(
    name='randomtools',
    version='1.0.0',
    description='A package that provides all maintenance tasks',
    author='Michał Moroz <michal@makimo.pl>',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ],
    packages=('randomtools',),
    package_dir={'': 'src'},
    install_requires=['docopt', 'thefuzz'],
    python_requires='>=3',
    entry_points={
        'console_scripts': [
            'copiesfromcsv = randomtools.copiesfromcsv:main',
            'sodamatcher = randomtools.sodamatcher:main',
            'movetoguids = randomtools.movetoguids:main',
            'maptocsvcolumn = randomtools.maptocsvcolumn:main',
        ],
    }
)
