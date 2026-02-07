"""
SkillPilot - EDA Tool Orchestration System

A system for orchestrating EDA tools via PTY sessions with file-based control plane.
"""

from setuptools import setup, find_packages

with open("README.md") as f:
    long_description = f.read()

setup(
    name="skillpilot",
    version="1.0.0",
    description="EDA Tool Orchestration System",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="SkillPilot Team",
    python_requires=">=3.8",
    packages=find_packages(exclude=["tests", "examples", "*.tests", "*.examples"]),
    install_requires=[
        "pyyaml>=5.4",
    ],
    entry_points={
        "console_scripts": [
            "skillpilot=skillpilot.cli.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Testing",
    ],
)
