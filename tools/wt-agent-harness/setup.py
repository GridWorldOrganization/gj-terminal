from setuptools import setup, find_packages

setup(
    name="windowsterminal-cli",
    version="0.1.0",
    description="CLI-Anything harness for Windows Terminal external API (send_text / get_buffer / set_font_size)",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=["click>=8.0"],
    entry_points={
        "console_scripts": [
            "wt-api=windowsterminal_cli.cli:main",
        ],
    },
)
