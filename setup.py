import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="mailboxzero",
    version="0.0.1",
    author="Tim Head",
    author_email="betatim@gmail.com",
    description="A simple smtp and webserver for throwaway email addresses",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/betatim/mailboxzero",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=["aiosmtpd", "tornado", "urlextract"],
    entry_points={
        "console_scripts": [
            "mailboxzero = mailboxzero:main",
        ],
    },
)
