import json, os, shutil, subprocess, tempfile
from pathlib import Path


def find_codex_executable() -> str:
    """Находит Codex даже когда Streamlit не получил пользовательский PATH."""
    from_path = shutil.which("codex")
    if from_path:
        return from_path

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates = sorted(
            (Path(local_app_data) / "OpenAI" / "Codex" / "bin").glob("*/codex.exe"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return str(candidates[0])

    raise FileNotFoundError(
        "Не найден codex.exe. Запустите Codex Desktop хотя бы один раз "
        "или добавьте каталог Codex в PATH."
    )

def ask_codex(prompt,schema,project,model=None,use_local_oss_model=False,local_provider="ollama",timeout_seconds=90):
    """Запускает Codex CLI и возвращает проверяемый JSON."""
    with tempfile.TemporaryDirectory() as temp:
        p=Path(temp); schema_file=p/"schema.json"; answer=p/"answer.json"
        schema_file.write_text(json.dumps(schema,ensure_ascii=False),encoding="utf-8")
        cmd=[find_codex_executable(),"exec","--ephemeral","--sandbox","read-only","--skip-git-repo-check","--cd",str(project),"--output-schema",str(schema_file),"--output-last-message",str(answer)]
        if model: cmd.extend(["--model",model])
        if use_local_oss_model: cmd.extend(["--oss","--local-provider",local_provider])
        # Длинный контекст по скважинам нельзя передавать аргументом командной
        # строки: Windows ограничивает её длину. Codex штатно читает задание из stdin.
        cmd.append("-")
        environment=os.environ.copy()
        if not environment.get("CODEX_HOME") and environment.get("USERPROFILE"):
            environment["CODEX_HOME"]=str(Path(environment["USERPROFILE"])/".codex")
        completed=subprocess.run(cmd,check=False,timeout=timeout_seconds,capture_output=True,input=prompt,text=True,encoding="utf-8",errors="replace",env=environment)
        if completed.returncode != 0:
            detail=(completed.stderr or completed.stdout or "нет диагностического сообщения").strip()
            if 'readonly database' in detail.lower() or ('arg0' in detail and ('os error 5' in detail or 'Отказано в доступе' in detail)):
                raise RuntimeError('Codex не имеет доступа к служебной папке пользователя. Если витрина запущена из песочницы Codex, запустите run_dashboard.ps1 из своего обычного PowerShell. Не меняйте права .codex и не удаляйте её базу.')
            raise RuntimeError(f"Codex завершился с кодом {completed.returncode}: {detail[-2000:]}")
        if not answer.exists():
            raise RuntimeError("Codex не создал файл ответа: "+completed.stderr[-1000:])
        return json.loads(answer.read_text(encoding="utf-8"))
