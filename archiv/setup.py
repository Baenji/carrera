"""
Setup script for DS-Carrera-v1 package.
"""
from setuptools import setup, find_packages
import os

# Read requirements
with open('requirements.txt') as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

# Read README
readme = ""
if os.path.exists('README.md'):
    with open('README.md', encoding='utf-8') as f:
        readme = f.read()

setup(
    name='ds-carrera',
    version='2.0.0',
    description='Computer vision and RL system for Carrera slot car racing track',
    long_description=readme,
    long_description_content_type='text/markdown',
    author='DS-Carrera Team',
    packages=find_packages(),
    include_package_data=True,
    python_requires='>=3.8',
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'carrera-track=src.main:main',
        ],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
        'Topic :: Scientific/Engineering :: Image Recognition',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
