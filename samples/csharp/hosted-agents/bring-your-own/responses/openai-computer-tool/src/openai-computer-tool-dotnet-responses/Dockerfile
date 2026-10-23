# Multi-stage Dockerfile for the C# OpenAI Computer Tool Hosted Agent.
# Uses the VirtualPaintDesktop (1280x800 pure managed framebuffer + PNG encoder)
# inside the container so no native X11 or GUI dependencies are required.

FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

# Copy project file and restore dependencies first (layer caching)
COPY openai-computer-tool.csproj .
RUN dotnet restore

# Copy remaining source and publish
COPY . .
RUN dotnet publish -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app

COPY --from=build /app .

# Switch to non-root user for security
USER $APP_UID

# Expose default hosted agent server port
EXPOSE 8088

ENTRYPOINT ["dotnet", "openai-computer-tool.dll"]
