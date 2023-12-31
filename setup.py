import os
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="spotify-cmd",
    version="0.1.4",
    packages=find_packages(),
    install_requires=[
        'argparse==1.4.0',
        'configparser==5.0.2',
        'spotipy==2.23.0',
        'python-daemon==3.0.1'
    ],
    entry_points={
        'console_scripts': [
            'spotify-cmd = src.spotify_cmd_client.main:main',
            'spotify-cmd-daemon = src.spotify_cmd_daemon.main:main'
        ]
    },
    author="Maciej Ciemborowicz",
    author_email="maciej.ciemborowicz@gmail.com",
    description="Command line Spotify client",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ciembor/spotify-cmd",
    license="GNU General Public License v3.0",
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: End Users/Desktop',
        'Topic :: Multimedia :: Sound/Audio :: Players',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Natural Language :: English',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
