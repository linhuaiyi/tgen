from setuptools import setup
from setuptools import find_packages


setup(
    name='tgen',
    version='0.2.0',
    description='Sequence-to-sequence natural language generator',
    author='Ondrej Dusek',
    author_email='odusek@ufal.mff.cuni.cz',
    url='https://github.com/UFAL-DSG/tgen',
    download_url='https://github.com/UFAL-DSG/tgen.git',
    license='Apache 2.0',
    install_requires=['regex',
                      'unicodecsv',
                      'enum34',
                      'numpy',
                      'rpyc',
                      'pudb',
                      'recordclass',
                      'tensorflow==1.0.1',
                      'kenlm',
                      'pytreex==0.1dev'],
    dependency_links=['https://storage.googleapis.com/tensorflow/linux/cpu/tensorflow-1.0.1-cp27-none-linux_x86_64.whl#egg=tensorflow-1.0.1',
                      'https://github.com/kpu/kenlm/archive/master.zip#egg=kenlm',
                      'https://github.com/ufal/pytreex/tarball/master#egg=pytreex-0.1dev'],
    packages=find_packages()
)

