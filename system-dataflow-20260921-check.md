# Проверка схемы 21.09.2026

- diagram_type: dataflow
- output: C:/work-scripts/First_AI_agent/system-dataflow-20260921.html
- specification_sha256: 1a009806dc17ba07d3169cde8533500deecafd323b7ed74b2dc802a4846e755c
- artifact_sha256: 0b47e6678a07160d55edbb1424caa10cd1c14e1c8ae784922805919b884b1cf8
- validation: 9/9 showcase, 0 errors, 0 warnings
- browser_evidence: failed (стандартный visual-check: Chrome GPU недоступен в песочнице; повтор вне песочницы дважды не получил решение проверки разрешения вовремя)
- visual_review: passed (просмотрены отдельные снимки большого светлого и малого тёмного вида)
- correction_rounds: 1

Дополнительная проверка через Playwright, tools/verify_current_diagram.cjs: 1440×900, 1600×1000, 1920×1080, 2048×1320 — scrollWidth/scrollHeight не превышают окно. Снимки data/diagram-20260921-large.png и data/diagram-20260921-small-other-theme.png. Это отдельное подтверждение, не успешный официальный visual-check. Старые process-archify.html и system-dataflow.html сохранены. Подписи русские, встроенный интерфейс Archify английский.
