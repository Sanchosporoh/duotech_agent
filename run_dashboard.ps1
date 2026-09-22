param([int]$Port = 8503)
$projectDirectory = $PSScriptRoot
$localPython = Join-Path $projectDirectory '.venv\Scripts\python.exe'
$sharedPython = 'C:\work-scripts\venv\Scripts\python.exe'
$pythonExecutable = if (Test-Path $localPython) { $localPython } elseif (Test-Path $sharedPython) { $sharedPython } else { 'python' }
& $pythonExecutable -m streamlit run (Join-Path $projectDirectory 'dashboard.py') --server.port $Port --server.headless true
