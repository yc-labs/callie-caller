# Use a stable, modern version of Python as the base image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /usr/src/app

# Install all necessary system dependencies for building PJSIP and SWIG
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libasound2-dev \
    libasound2-plugins \
    portaudio19-dev \
    wget \
    tar \
    python3-lib2to3 \
    swig \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Download and unpack the LATEST PJSIP source code (version 2.15.1)
RUN wget https://github.com/pjsip/pjproject/archive/refs/tags/2.15.1.tar.gz && \
    tar -xvf 2.15.1.tar.gz

# Enter the source directory, configure, compile, and build the project.
RUN cd pjproject-2.15.1 && \
    export CFLAGS="$CFLAGS -fPIC" && \
    ./configure --enable-shared && \
    make dep && \
    make && \
    make install && \
    ldconfig

# --- FIX #1 for TabError ---
# The original setup.py has mixed tabs and spaces.
RUN sed -i 's/\t/    /g' pjproject-2.15.1/pjsip-apps/src/python/setup.py

# --- FIX #2 for SyntaxError ---
# The setup.py script uses Python 2 'print' syntax.
RUN 2to3 -w pjproject-2.15.1/pjsip-apps/src/python/setup.py

# --- FIX #3 for NameError ---
# The setup.py script has a logical bug where 'tokens' may not be defined.
# This command injects a line to initialize it, fixing the bug.
RUN sed -i '1itokens = []' pjproject-2.15.1/pjsip-apps/src/python/setup.py

# Build and install the modern PJSUA2 Python bindings (SWIG based)
RUN cd pjproject-2.15.1/pjsip-apps/src/swig/python && \
    make && \
    make install

# Copy the requirements file and install Python dependencies
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Copy your application code into the container
COPY src/ ./src/
COPY main.py .
COPY api.py .

# Set PYTHONPATH to include the pjsua2 module
ENV PYTHONPATH=/usr/src/app/pjproject-2.15.1/pjsip-apps/src/swig/python:/usr/src/app/src:$PYTHONPATH

# Set the command that will run when the container starts
CMD ["python3", "-u", "./main.py"]
