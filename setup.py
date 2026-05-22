from setuptools import setup, find_packages

setup(
    name="groove-analyzer",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["mido>=1.3", "matplotlib>=3.8", "numpy>=1.24"],
    python_requires=">=3.9",
)
