import setuptools

if __name__ == "__main__":
    setuptools.setup(
        name='gynt',

        version="0.1",

        description='Peer To Peer File Transfer',

        author='Nils Werner',
        author_email='nils.werner@gmail.com',

        license='MIT',

        packages=setuptools.find_packages(),

        install_requires=[
            'zeroconf',
        ],

        extras_require={
            'docs': [
                'sphinx',
                'sphinxcontrib-napoleon',
                'sphinx_rtd_theme',
                'numpydoc',
            ],
            'tests': [
                'pytest',
                'pytest-cov',
                'pytest-pep8',
            ],
        },

        tests_require=[
            'pytest',
            'pytest-cov',
            'pytest-pep8',
        ],

        classifiers=[
            'Development Status :: 3 - Alpha',
            'Environment :: Console',
            'Programming Language :: Python :: 2.7',
            'Programming Language :: Python :: 3',
            'License :: OSI Approved :: MIT License',
            'Topic :: Communications :: File Sharing',
            'Topic :: Internet :: WWW/HTTP',
            'Topic :: Utilities',
        ],

        entry_points={'console_scripts': [
            'gynt=gynt.get:get',
            'pynt=gynt.put:put'
        ]},
    )
