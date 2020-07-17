import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="maximo-gui-connector", 
    version="0.0.1",
    author="Luca Salvarani",
    author_email="lucasalvarani99@gmail.com",
    description="Small Library that makes it easier to create scripts to automate IBM Maximo's frontend",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/LukeSavefrogs/maximo-gui-connector",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.0',
	install_requires=["selenium"],
)
