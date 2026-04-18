from setuptools import setup, find_packages


with open("README.md", "r", encoding="utf-8") as f:
    description = f.read()

setup(
    name="tokenmap",
    version="0.1.1",
    author="Akshat Shaw",
    description="GitHub-style contribution heatmap for your AI coding tool usage. Supports Claude Code, Codex, OpenCode & Cursor.",
    long_description=description,
    long_description_content_type="text/markdown",
    url="https://github.com/akshatshaw/tokenmap-python",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0",
        "rich>=13.0",
        "pymupdf>=1.24.0",
        "httpx>=0.24",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21",
        ],
    },
    entry_points={
        "console_scripts": [
            "tokenmap = tokenmap.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Software Development :: Libraries",
        "Topic :: Utilities",
    ],
    keywords=[
        "cli", "heatmap", "contribution-graph", "github-style",
        "claude-code", "claude", "codex", "opencode", "cursor",
        "ai", "ai-tools", "coding-assistant", "usage", "tokens",
        "statistics", "terminal", "developer-tools", "devtools",
    ],
)
