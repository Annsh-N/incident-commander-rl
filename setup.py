from setuptools import find_packages, setup


setup(
    name="incident-commander-env",
    version="0.1.0",
    description="Deterministic Incident Commander reinforcement learning environment.",
    python_requires=">=3.10",
    packages=find_packages(),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "ic=incident_commander_env.cli:main",
        ]
    },
    extras_require={
        "gym": ["gymnasium>=0.29,<2"],
        "test": ["pytest>=8,<9"],
    },
)
