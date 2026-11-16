# Multi-stage Dockerfile for the C# OpenAI Computer Tool Hosted Agent.
# Uses the VirtualPaintDesktop (1280x800 pure managed framebuffer + PNG encoder)
# inside the container so no native X11 or GUI dependencies are required.

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src

# Copy project file and restore dependencies first (layer caching).
# The runtime identifier and ReadyToRun flag must match between restore and
# publish, otherwise publish fails with NETSDK1094.
COPY openai-computer-tool.csproj .
RUN dotnet restore -r linux-x64 -p:PublishReadyToRun=true

# Copy remaining source and publish ReadyToRun: precompile IL to native code
# for the target runtime so the JIT does far less work during container start.
# --self-contained false keeps the framework-dependent layout, so this costs
# image size but not a runtime dependency.
COPY . .
RUN dotnet publish -c Release -r linux-x64 --self-contained false -p:PublishReadyToRun=true -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app

COPY --from=build /app .

# Switch to non-root user for security
USER $APP_UID

# Expose default hosted agent server port
EXPOSE 8088

ENTRYPOINT ["dotnet", "openai-computer-tool.dll"]
