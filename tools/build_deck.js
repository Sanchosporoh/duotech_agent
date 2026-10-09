// Stakeholder deck (course passport Р8). Every number comes from course/passport.md.
// Needs pptxgenjs (npm install pptxgenjs in any folder, then NODE_PATH=<folder>/node_modules) and the NS Digital skill assets.
// Run: node tools/build_deck.js course/deck/agent_deck.pptx
const PptxGenJS = require('pptxgenjs');
const path = require('path');

const ASSETS = 'C:/Users/User1/AppData/Roaming/Claude/local-agent-mode-sessions/skills-plugin/8ef7bff0-8766-413f-811a-33353097c79b/2def231b-836c-444a-8398-f62454ae1964/skills/ns-digital-pptx/assets';
const OUT = process.argv[2];
const ONLY = process.env.ONLY;

const pptx = new PptxGenJS();
pptx.defineLayout({ name: 'NSD', width: 13.33, height: 7.5 });
pptx.layout = 'NSD';
pptx.title = 'Агент контроля добычи куста';

const C = { purple: '41008C', navy: '19003C', green: '00DD00', tint: 'CCF6C6', orange: 'ED7F34',
  gray: 'A7A6A6', card: 'F2F2F2', card2: 'E7E7E7', white: 'FFFFFF', lpurple: '9C78C3' };
// Arial: the NS brand font for office documents; Golos Text is often missing and breaks line wrapping.
const F = 'Arial', FB = 'Arial';

function chrome(slide, page) {
  slide.background = { color: C.white };
  slide.addShape(pptx.ShapeType.rect, { x: 12.18, y: 0, w: 1.15, h: 7.5, fill: { color: C.purple }, line: { type: 'none' } });
  slide.addImage({ path: path.join(ASSETS, 'ns_badge.png'), x: 12.52, y: 0.28, w: 0.48, h: 0.36 });
  slide.addText(String(page), { x: 11.4, y: 7.0, w: 0.6, h: 0.3, fontSize: 12, color: C.gray, fontFace: F, align: 'right' });
}

function header(slide, topic, subtitle) {
  slide.addText([
    { text: 'NS Digital', options: { color: C.purple, bold: true } },
    { text: ' / ' + topic, options: { color: C.navy, bold: false } }
  ], { x: 0.45, y: 0.18, w: 10.9, h: 0.7, fontSize: 32, fontFace: FB, valign: 'middle', margin: 0 });
  slide.addShape(pptx.ShapeType.line, { x: 0.45, y: 0.95, w: 10.9, h: 0, line: { color: C.gray, width: 0.75 } });
  if (subtitle) slide.addText(subtitle.toUpperCase(), { x: 0.45, y: 1.05, w: 10.9, h: 0.6,
    fontSize: 17, bold: true, color: C.navy, fontFace: FB, valign: 'top', margin: 0 });
}

function cta(slide, text, y = 6.2, w = 11.1) {
  slide.addShape(pptx.ShapeType.roundRect, { x: 0.45, y, w, h: 0.7, fill: { color: C.green }, line: { type: 'none' }, rectRadius: 0.12 });
  slide.addText(text, { x: 0.7, y, w: w - 0.5, h: 0.7, fontSize: 14, bold: true, color: C.white, fontFace: FB, valign: 'middle', margin: 0 });
}

function note(slide, text, y = 6.95) {
  slide.addText(text, { x: 0.45, y, w: 10.8, h: 0.35, fontSize: 9, color: C.gray, fontFace: F, valign: 'middle', margin: 0 });
}

// ---------- 1. Title ----------
if (!ONLY || ONLY==='1') {
  const s = pptx.addSlide();
  s.background = { color: C.white };
  s.addImage({ path: path.join(ASSETS, 'ns_digital_logo.png'), x: 0.6, y: 0.5, w: 2.4, h: 0.62, sizing: { type: 'contain', w: 2.4, h: 0.62 } });
  s.addShape(pptx.ShapeType.rect, { x: 0, y: 2.55, w: 13.33, h: 2.75, fill: { color: '3C3C3C' }, line: { type: 'none' } });
  s.addText('АГЕНТ КОНТРОЛЯ\nДОБЫЧИ КУСТА', { x: 0.6, y: 2.65, w: 8.2, h: 1.75, fontSize: 44, bold: true, color: C.white, fontFace: FB, valign: 'middle', margin: 0 });
  s.addText('Недобор нефти найден и рассчитан за 1.5 часа вместо 10', { x: 0.6, y: 4.4, w: 8.2, h: 0.7, fontSize: 18, color: C.white, fontFace: F, valign: 'middle', margin: 0 });
  s.addImage({ path: path.join(ASSETS, 'lineart_refinery.svg'), x: 8.9, y: 0.9, w: 4.1, h: 6.0, sizing: { type: 'contain', w: 4.1, h: 6.0 } });
  s.addText('Паспорт агента · Блок 3 «Agentic Workflow» · октябрь 2026', { x: 0.6, y: 6.6, w: 8.0, h: 0.4, fontSize: 12, color: C.gray, fontFace: F, margin: 0 });
}

// ---------- 2. Problem ----------
if (!ONLY || ONLY==='2') {
  const s = pptx.addSlide(); chrome(s, 2);
  header(s, 'Проблема', 'Недобор замечают и считают вручную — компенсация начинается через 18 часов');
  const cards = [
    ['18 ч', 'от обнаружения отклонения до действия на скважинах'],
    ['10 ч', 'из них — обнаружение отклонения и ручной расчёт в PetEx'],
    ['10.7 т', 'нескомпенсированной нефти на один инцидент — 213 тыс. руб'],
    ['552 мин', 'в неделю инженера-моделиста на проверке гипотез и расчёте режима'],
  ];
  cards.forEach(([big, text], i) => {
    const x = 0.45 + i * 2.8;
    s.addShape(pptx.ShapeType.rect, { x, y: 2.0, w: 2.6, h: 3.0, fill: { color: C.card }, line: { type: 'none' } });
    s.addText(big, { x: x + 0.15, y: 2.2, w: 2.3, h: 1.1, fontSize: 40, bold: true, color: i === 2 ? C.green : C.purple, fontFace: FB, margin: 0 });
    s.addText(text, { x: x + 0.15, y: 3.4, w: 2.3, h: 2.0, fontSize: 14, color: C.navy, fontFace: F, valign: 'top', margin: 0 });
  });
  cta(s, 'Потеря нефти растёт каждый час, пока отклонение ждёт человека и ручного расчёта');
  note(s, 'Источник: отчёт по диагностическому аудиту бизнес-процессов Заказчика (18 ч / 10 ч). Нефть — расчёт на учебном кейсе: потеря 14.2 т/сут × 18 ч / 24, 20 000 руб/т.');
}

// ---------- 3. As-Is ----------
if (!ONLY || ONLY==='3') {
  const s = pptx.addSlide(); chrome(s, 3);
  header(s, 'Как сейчас (As-Is)', 'Узкое место — ручная проверка гипотез и расчёт режима: 46 % времени');
  const head = ['№', 'Шаг', 'Кто', 'Мин', 'Раз / нед', 'Потеря, мин / нед'];
  const rows = [
    ['0', 'Двухчасовка с добычей по сепаратору — отклонение видно только при просмотре', 'регламент', '—', '—', '—'],
    ['1', 'Выгрузить телеметрию и замеры', 'инженер, скрипт', '20', '5', '100'],
    ['2', 'Отбраковать замеры', 'скрипт + инженер', '60', '5', '300'],
    ['3', 'Сформулировать гипотезы', 'технолог', '60', '2.3', '138'],
    ['4', 'Проверить гипотезы расчётом в ИМА', 'инженер-моделист', '120', '2.3', '276'],
    ['5', 'Рассчитать режим куста и утвердить', 'моделист, технолог', '120', '2.3', '276'],
    ['6', 'Согласовать с цехом, внести уставки', 'начальник ЦДНГ', '20', '2.3', '46'],
    ['7', 'Сравнить факт с прогнозом', 'скрипт', '15', '5', '75'],
  ];
  const cell = (t, o = {}) => ({ text: t, options: Object.assign({ fontFace: F, fontSize: 12, color: C.navy, valign: 'middle' }, o) });
  const data = [head.map(h => cell(h, { bold: true, fontFace: FB, fill: { color: C.card2 } }))];
  rows.forEach(r => {
    const hot = r[0] === '4' || r[0] === '5';
    data.push(r.map((t, j) => cell(t, Object.assign(hot ? { fill: { color: C.tint }, bold: j === 5 } : {}, j >= 3 ? { align: 'center' } : {}))));
  });
  s.addTable(data, { x: 0.45, y: 1.85, w: 11.1, colW: [0.45, 5.0, 2.0, 0.8, 1.15, 1.7], rowH: 0.42,
    border: { type: 'solid', pt: 0.5, color: C.gray } });
  cta(s, 'Шаги 4–5: 552 из 1 211 мин в неделю (46 %) и 10 из 18 ч задержки действия', 5.85);
  note(s, 'Минуты и частота — таблица части 1 (экспертная оценка), сведены с 10 ч аудита: 380 мин работы + 220 мин ожидания двухчасовки и начала разбора.', 6.65);
}

// ---------- 4. To-Be ----------
if (!ONLY || ONLY==='4') {
  const s = pptx.addSlide(); chrome(s, 4);
  header(s, 'Как будет (To-Be)', 'Ежечасный контроль и расчёт по событию; решение остаётся за инженером');
  const steps = [
    ['Т1', 'Принять и проверить замеры', 'workflow', false],
    ['Т2', 'Обнаружить отклонение', 'workflow', false],
    ['Т3', 'Диагноз: гипотезы + PROSPER', 'агент', true],
    ['Т4', 'Компенсация: наборы + GAP', 'агент', true],
    ['Т5', 'Утвердить / вернуть', 'технолог', false],
    ['Т6', 'Согласовать с цехом', 'начальник ЦДНГ', false],
  ];
  steps.forEach(([id, text, who, agent], i) => {
    const x = 0.45 + i * 1.86;
    s.addShape(pptx.ShapeType.chevron, { x, y: 1.95, w: 1.8, h: 1.25, fill: { color: agent ? C.green : C.card }, line: { type: 'none' } });
    s.addText(id, { x: x + 0.3, y: 1.95, w: 1.2, h: 1.25, fontSize: 22, bold: true, color: agent ? C.white : C.purple, fontFace: FB, align: 'center', valign: 'middle', margin: 0 });
    s.addText(text, { x, y: 3.3, w: 1.75, h: 0.75, fontSize: 12, color: C.navy, fontFace: F, align: 'center', valign: 'top', margin: 0 });
    s.addText(who.toUpperCase(), { x, y: 4.05, w: 1.75, h: 0.35, fontSize: 10, bold: true, color: agent ? C.purple : C.gray, fontFace: FB, align: 'center', margin: 0 });
  });
  const cols = [
    ['ЧТО ПЕРЕПРОЕКТИРОВАНО', 'Сравнение факта с прогнозом — триггер в начале, а не отчёт в конце. Гипотезы и проверка расчётом — один шаг по событию. Расчёт режима отделён от утверждения.'],
    ['КАК РАБОТАЕТ АГЕНТ', 'LLM предлагает гипотезы и наборы мероприятий, PROSPER и GAP проверяют их физикой и ограничениями сети, код выбирает лучший допустимый вариант.'],
    ['ОСТАВЛЕНО ЧЕЛОВЕКУ', 'Решение по режиму (необратимо, ответственность именная) и согласование с цехом (переговоры, нет программного входа).'],
  ];
  cols.forEach(([h, t], i) => {
    const x = 0.45 + i * 3.72;
    s.addShape(pptx.ShapeType.rect, { x, y: 4.55, w: 3.55, h: 1.9, fill: { color: C.card }, line: { type: 'none' } });
    s.addText(h, { x: x + 0.15, y: 4.62, w: 3.25, h: 0.4, fontSize: 12, bold: true, color: C.purple, fontFace: FB, margin: 0 });
    s.addText(t, { x: x + 0.15, y: 5.02, w: 3.25, h: 1.4, fontSize: 11, color: C.navy, fontFace: F, valign: 'top', margin: 0 });
  });
  note(s, 'Агентных шагов 2 из 6. Данные не покидают сеть компании: LLM — GPT-OSS 120B на сервере LM Studio; облачные модели запрещены в конфигурации.', 6.6);
}

// ---------- 5. Metrics ----------
if (!ONLY || ONLY==='5') {
  const s = pptx.addSlide(); chrome(s, 5);
  header(s, 'Метрики', 'Значения «до» — из аудита и листа As-Is; «после» — замеры прототипа');
  const kpi = [
    ['Обнаружение и расчёт', '10 ч', '≤ 1.5 ч', 'журнал тактов агента'],
    ['От обнаружения до действия', '18 ч', '≈ 9.5 ч', 'журнал + время решения'],
    ['Нескомпенсированная нефть на инцидент', '10.7 т', '5.6 т', 'потеря темпа × время / 24'],
    ['Время инженера-моделиста', '552 мин/нед', 'только эскалации', 'очередь эскалаций'],
  ];
  kpi.forEach(([name, before, after, how], i) => {
    const y = 1.85 + i * 0.95;
    s.addShape(pptx.ShapeType.rect, { x: 0.45, y, w: 11.1, h: 0.85, fill: { color: C.card }, line: { type: 'none' } });
    s.addText(name, { x: 0.6, y, w: 4.0, h: 0.85, fontSize: 14, bold: true, color: C.navy, fontFace: FB, valign: 'middle', margin: 0 });
    s.addText(before, { x: 4.6, y, w: 2.0, h: 0.85, fontSize: 24, color: C.gray, fontFace: FB, align: 'center', valign: 'middle', margin: 0 });
    s.addShape(pptx.ShapeType.rightArrow, { x: 6.7, y: y + 0.28, w: 0.55, h: 0.3, fill: { color: C.green }, line: { type: 'none' } });
    s.addText(after, { x: 7.35, y, w: 2.4, h: 0.85, fontSize: after.length > 9 ? 16 : 24, bold: true, color: C.purple, fontFace: FB, align: 'center', valign: 'middle', margin: 0 });
    s.addText(how, { x: 9.8, y, w: 1.7, h: 0.85, fontSize: 10, color: C.gray, fontFace: F, valign: 'middle', margin: 0 });
  });
  cta(s, 'Проверено: eval-набор 15 из 15; серия пяти прогонов на PetEx — 5 из 5 успешных', 5.8);
  note(s, 'Серия пяти прогонов — учебные сутки, облачная модель прототипа. Локальная GPT-OSS 120B: пробные вызовы, серия — в shadow.', 6.6);
}

// ---------- 6. Rollout ----------
if (!ONLY || ONLY==='6') {
  const s = pptx.addSlide(); chrome(s, 6);
  header(s, 'Запуск', 'Пилот 01.12.2026–25.01.2027: 7 кустов, ~105 скважин, ~1 инцидент в сутки');
  const stages = [
    ['SHADOW', '2 недели', 'Агент считает по реальным данным, инженер работает как раньше, решения сравниваются', '≥ 10 инцидентов; 80 % — готовое предложение; причина совпала в 70 %; 0 нарушений ограничений'],
    ['HITL', '4 недели', 'Предложения идут технологу на утверждение, затем согласование с цехом', '≥ 20 утверждённых; ≥ 70 % без переделки; факт в пределах прогноза ±5 %'],
    ['AUTONOMOUS', 'ограниченный', 'Агент ведёт контур до предложения и ставит задачу после утверждения; режим решает технолог', 'Откат в HITL: расхождение с прогнозом > 10 % дважды за неделю'],
  ];
  stages.forEach(([name, dur, what, crit], i) => {
    const x = 0.45 + i * 3.72;
    s.addShape(pptx.ShapeType.chevron, { x, y: 1.9, w: 3.6, h: 0.9, fill: { color: i === 0 ? C.green : C.card }, line: { type: 'none' } });
    s.addText(name, { x: x + 0.35, y: 1.9, w: 2.9, h: 0.9, fontSize: 18, bold: true, color: i === 0 ? C.white : C.purple, fontFace: FB, align: 'center', valign: 'middle', margin: 0 });
    s.addText(dur.toUpperCase(), { x, y: 2.9, w: 3.55, h: 0.35, fontSize: 11, bold: true, color: C.gray, fontFace: FB, margin: 0 });
    s.addText(what, { x, y: 3.25, w: 3.5, h: 1.1, fontSize: 12, color: C.navy, fontFace: F, valign: 'top', margin: 0 });
    s.addShape(pptx.ShapeType.line, { x, y: 4.4, w: 3.5, h: 0, line: { color: C.gray, width: 0.75 } });
    s.addText((i < 2 ? [{ text: 'Переход дальше: ', options: { bold: true, color: C.purple } }] : []).concat([{ text: crit, options: { color: C.navy } }]),
      { x, y: 4.5, w: 3.5, h: 1.3, fontSize: 11, fontFace: F, valign: 'top', margin: 0 });
  });
  cta(s, 'Немедленная остановка: данные за контуром, запись без утверждения, 2 рекомендации с нарушением ограничений', 5.95);
  note(s, 'Ответственный за починку — инженер-моделист ЦУД (круглосуточно), вторая линия — руководитель группы моделирования и оптимизации; риски и мониторинг — паспорт, Р7.', 6.7);
}

// ---------- 7. Cost ----------
if (!ONLY || ONLY==='7') {
  const s = pptx.addSlide(); chrome(s, 7);
  header(s, 'Стоимость', 'Окупается при ≥ 11.5 т нефти на куст в год');
  const left = [
    ['≈ 100 тыс. руб', 'сохранённой нефти на инцидент: ≈ 5 т, время до действия 18 ч → ≈ 9.5 ч'],
    ['≈ 1.9 млн ₽', 'пилот на 7 кустах: внедрение системы, месторождения и кустов + время людей; для Заказчика бесплатно, железо — нынешний сервер'],
    ['23 млн ₽', '100 кустов, 3 месторождения, первый год: железо 2 млн, внедрение 9 млн, сопровождение 12 млн; дальше ≈ 12.4 млн ₽ в год'],
  ];
  left.forEach(([big, text], i) => {
    const y = 1.9 + i * 1.3;
    s.addText(big, { x: 0.45, y, w: 3.6, h: 1.1, fontSize: 32, bold: true, color: i === 0 ? C.green : C.purple, fontFace: FB, valign: 'middle', margin: 0 });
    s.addText(text, { x: 4.1, y, w: 3.3, h: 1.1, fontSize: 12, color: C.navy, fontFace: F, valign: 'middle', margin: 0 });
  });
  s.addShape(pptx.ShapeType.rect, { x: 7.7, y: 1.9, w: 3.85, h: 3.75, fill: { color: C.card }, line: { type: 'none' } });
  s.addText('ПОРОГ ОКУПАЕМОСТИ', { x: 7.9, y: 2.0, w: 3.5, h: 0.4, fontSize: 12, bold: true, color: C.purple, fontFace: FB, margin: 0 });
  s.addText([
    { text: 'первый год: 23 млн ₽ ÷ 100 кустов ≈ 11.5 т нефти на куст', options: { breakLine: true } },
    { text: 'следующие годы: ≈ 6.2 т на куст', options: { breakLine: true } },
    { text: 'один инцидент типичной скважины (60 м³/сут, 30 % воды) — ≈ 10.9 т', options: { breakLine: true } },
    { text: ' ', options: { breakLine: true } },
    { text: 'ПОТОЛКИ', options: { bold: true, color: C.purple, breakLine: true } },
    { text: '20 вызовов LLM и 30 GAP в сутки, $1.5 в сутки, такт 45 мин; после потолка агент стоит до разбора' },
  ], { x: 7.9, y: 2.45, w: 3.5, h: 3.1, fontSize: 12, color: C.navy, fontFace: F, valign: 'top', margin: 0, paraSpaceAfter: 4 });
  cta(s, 'Почему не оставить как есть: каждый инцидент — ≈ 5 т нефти (≈ 100 тыс. руб), потерянных за 8.5 лишних часов', 5.95);
  note(s, 'Учебный кейс: потеря 14.2 т/сут, 20 000 руб/т, 8 ч после расчёта без изменений. Внедрение и сопровождение — оценка; эффект в год даст пилот.', 6.7);
}

pptx.writeFile({ fileName: OUT }).then(f => console.log('written', f));
