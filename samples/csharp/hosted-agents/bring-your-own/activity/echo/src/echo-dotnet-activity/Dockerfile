FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY . .
RUN dotnet publish echo.csproj -c Release -r linux-x64 --self-contained false -p:PublishReadyToRun=true -o /app

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /app .
ENV PORT=8088
EXPOSE 8088
USER $APP_UID
ENTRYPOINT ["dotnet", "echo.dll"]
