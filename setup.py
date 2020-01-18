#!/usr/bin/env python
from setuptools import setup, find_packages
import liaa

# pylint: disable=bad-continuation
setup(
		name="liaa",
		version=liaa.__version__,
		# pylint: disable=line-too-long
		description="Liaa is a distributed hash table for decentralized peer-to-peer computer networks.",
		long_description=open("./docs/README.md", encoding='utf-8').read(),
		long_description_content_node_type='text/markdown',
		author="Brian Muller, Rashad Alston",
		author_email="bamuller@gmail.com, rashadalston@gmail.com",
		license="MIT",
		url="http://github.com/ralston3/liaa",
		packages=find_packages(),
		install_requires=open("requirements.txt").readlines(),
		classifiers=[
			"Development Status :: 5 - Production/Stable",
			"Intended Audience :: Developers",
			"License :: OSI Approved :: MIT License",
			"Operating System :: OS Independent",
			"Programming Language :: Python",
			"Programming Language :: Python :: 3",
			"Programming Language :: Python :: 3.5",
			"Programming Language :: Python :: 3.6",
			"Programming Language :: Python :: 3.7",
			"Topic :: Software Development :: Libraries :: Python Modules",
		],
)
