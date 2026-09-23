FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY . .
RUN dotnet publish -c Release -r linux-x64 --self-contained false -p:PublishReadyToRun=true -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
COPY --from=build /app/publish .
EXPOSE 8088
ENV ASPNETCORE_URLS=http://+:8088
ENTRYPOINT ["dotnet", "resilient-workflow.dll"]
