$ContainerName = "finally-app"
docker stop $ContainerName 2>$null
docker rm $ContainerName 2>$null
Write-Host "FinAlly stopped. Your data is preserved in db/finally.db"
