from setuptools import setup, find_packages

setup(
    name="windowsterminal-cli",
    version="0.2.0",
    description="CLI + MCP (gj-terminal-plus) harness for the Windows Terminal external control API",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=["click>=8.0", "mcp>=1.0"],
    entry_points={
        "console_scripts": [
            "wt-api=windowsterminal_cli.cli:main",
            "wt-mcp=windowsterminal_cli.mcp_server:main",
        ],
    },
)
