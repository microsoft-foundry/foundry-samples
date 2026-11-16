FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY . .
RUN dotnet publish github-copilot.csproj -c Release -r linux-x64 --self-contained false -p:PublishReadyToRun=true -o /app

FROM mcr.microsoft.com/dotnet/aspnet:10.0
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/documents \
    && /opt/documents/bin/pip install --no-cache-dir python-docx==1.2.0 python-pptx==1.0.2 reportlab==4.4.4
ENV PATH="/opt/documents/bin:${PATH}"
ENV HOME=/home/app
WORKDIR /app
COPY --from=build /app .
ENV PORT=8088
EXPOSE 8088
USER $APP_UID
ENTRYPOINT ["dotnet", "github-copilot.dll"]
