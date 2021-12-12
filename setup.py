from setuptools import setup, find_packages

setup(
    name='roy',
    version='0.5',
    description="""Deploy and app configuration made easy.""",
    url='http://github.com/royprojectcom/roy',
    author='Morty Space',
    author_email='morty.space@gmail.com',
    license='MIT',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: Implementation :: CPython',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    package_dir={'': 'src'},
    packages=find_packages('src'),
    include_package_data=True,
    install_requires=[
        'cerberus',
        'jinja2',
        'watchgod'
    ],
    extras_require={
        'dev': [
            'pylint',
            'pycodestyle',
            'pytest',
            'pytest-cov',
            'pytest-env',
            'pytest-pythonpath',
            'autopep8',
            'sphinx',
            'twine',
            'setuptools',
            'wheel'
        ]
    },
    zip_safe=True,
    entry_points={
        'console_scripts': [
            'roy = roy.deploy.bin:run'
        ]
    }
)
