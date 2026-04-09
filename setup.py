from setuptools import setup, find_packages

setup(
    name="pyespargos",
    version="0.1.1",
    author="Florian Euchner",
    author_email="jeija@jeija.net",
    description="Python library for working with the ESPARGOS WiFi channel sounder",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/ESPARGOS/pyespargos",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.11",
    install_requires=["websockets>=12.0", "numpy>=1.26.0"],
    extras_require={
        # Runtime dependencies for the demo applications
        "demos": [
            "PyQt6>=6.6",
            "PyQt6-Charts>=6.6",
            "PyYAML>=6.0",
            "matplotlib>=3.7",
        ],
        # Additional dependencies for running tests
        "dev": [
            "PyQt6>=6.6",
            "PyQt6-Charts>=6.6",
            "PyYAML>=6.0",
            "matplotlib>=3.7",
            "pytest>=7.0",
            "pytest-qt>=4.0",
        ],
    },
    include_package_data=True,
)
