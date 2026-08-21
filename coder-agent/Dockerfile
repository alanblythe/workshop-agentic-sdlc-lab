# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM python:3.12-slim

# The agent clones a repository and pushes to it. The slim base has neither
# binary, and their absence surfaces as a clone failure that reads like a
# network or credential fault.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Pin GitHub's host keys at build time. Without them the first clone either
# prompts and hangs -- fatal inside a bounded invocation -- or has to be run
# with StrictHostKeyChecking disabled, which is the wrong trade for an agent
# that pushes.
RUN mkdir -p /etc/ssh && ssh-keyscan -t rsa,ecdsa,ed25519 github.com >> /etc/ssh/ssh_known_hosts

# git refuses to commit without an identity, and the agent commits every
# iteration. The error names a config setting, not the missing setup.
RUN git config --system user.name  "agentic-sdlc coder agent" \
 && git config --system user.email "coder-agent@agentic-sdlc.invalid"

RUN pip install --no-cache-dir uv==0.8.13

# The coding harness lives in its own interpreter. google-antigravity needs
# protobuf >= 7.35 at runtime; google-cloud-aiplatform, which serves the
# reasoning-engine routes :streamQuery dispatches to, caps protobuf below
# 7.0.0. One venv cannot hold both, and the failure is not a resolution error
# -- it is a VersionError raised when localharness_pb2 is imported.
COPY ./coder_runtime /opt/antigravity
RUN cd /opt/antigravity && uv sync --frozen --no-dev

WORKDIR /code

COPY ./pyproject.toml ./README.md ./uv.lock* ./

COPY ./app ./app

RUN uv sync --frozen

ARG AGENT_VERSION=0.0.0
ENV AGENT_VERSION=${AGENT_VERSION}

EXPOSE 8080

CMD ["uv", "run", "uvicorn", "app.fast_api_app:app", "--host", "0.0.0.0", "--port", "8080"]
