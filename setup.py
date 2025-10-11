from setuptools import setup, find_packages


with open("README.md", 'r', encoding='utf8') as fh:
    long_description = fh.read()

setup(
    name='api-watch',
    version='0.1.0',
    author="Isaac Kyalo",
    author_email="isadechair019@gmail.com",
    description="Real-time API monitoring for Flask/FastAPI with async, zero-blocking logging",
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/mount-isaac/api-watch',
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Monitoring",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Framework :: Flask",
        "Framework :: FastAPI",
    ],
    python_requires=">=3.7",
    install_requires=[
        "aiohttp>=3.8.0"
    ],
    extras_require={
        "flask": ["Flask>=2.0.0"],
        "fastapi": ["fastapi>=0.68.0", "starlette>=0.14.0"],
        "all": ["Flask>=2.0.0", "fastapi>=0.68.0", "starlette>=0.14.0"],
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.20.0",
            "black>=22.0.0",
            "flake8>=5.0.0",
            "Flask>=2.0.0",
            "fastapi>=0.68.0",
            "starlette>=0.14.0",
            "uvicorn>=0.31.0"
        ],
    },
    keywords="api monitoring flask fastapi logging debugging websocket real-time",
    project_urls={
        "Bug Reports": "https://github.com/mount-isaac/api-watch/issues",
        "Source": "https://github.com/mount-isaac/api-watch",
    }
)