# For CI deploy.yml to run, needs these deps that dont come default in cloud build.

FROM gcr.io/cloud-builders/docker

SHELL ["/bin/bash", "-c"]

RUN apt-get update

RUN apt-get install -y --no-install-recommends \
	ca-certificates \
	curl \
	gnupg

RUN mkdir -p /etc/apt/keyrings /usr/share/keyrings

RUN curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
	| gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg

RUN echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
	> /etc/apt/sources.list.d/nodesource.list

RUN curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
	| gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg

RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
	> /etc/apt/sources.list.d/google-cloud-sdk.list

RUN apt-get update

RUN apt-get install -y --no-install-recommends \
	nodejs \
	google-cloud-cli

RUN corepack enable

RUN rm -rf /var/lib/apt/lists/*