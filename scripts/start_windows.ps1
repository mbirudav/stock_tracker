param([switch]$Build)
$ContainerName = "finally-app"
$ImageName = "finally"

if ($Build -or -not (docker image inspect $ImageName 2>$null)) {
    Write-Host "Building FinAlly..."
    docker build -t $ImageName .
}

$running = docker ps -q -f "name=$ContainerName"
if ($running) {
    Write-Host "FinAlly is already running at http://localhost:8000"
    exit 0
}

docker run -d `
    --name $ContainerName `
    -p 8000:8000 `
    -v "${PWD}/db:/app/db" `
    --env-file .env `
    $ImageName

Write-Host "FinAlly started at http://localhost:8000"
Start-Process "http://localhost:8000"
