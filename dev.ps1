# PharosDB dev launcher
# frontend: http://localhost:17000
# backend:  http://localhost:17080

# kill any leftover processes on the two ports
foreach ($port in @(17000, 17080)) {
    $pids = (netstat -ano | Select-String ":$port " | Select-String "LISTENING" |
             ForEach-Object { ($_ -split '\s+')[-1] }) | Select-Object -Unique
    foreach ($p in $pids) {
        if ($p -match '^\d+$') {
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
            Write-Host "killed pid $p (port $port)"
        }
    }
}

Start-Sleep -Seconds 1

# backend
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "cd '$PSScriptRoot'; python manage.py runserver 17080"

# frontend
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "cd '$PSScriptRoot\frontend'; npm run dev"

Write-Host ""
Write-Host "backend  -> http://localhost:17080"
Write-Host "frontend -> http://localhost:17000"
