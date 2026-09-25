"""Build course/passport.html from course/passport.md (readable version for the reviewer).

The review panel lists what the engineer has to check or approve; edit REVIEW below.
Run: python tools/build_passport_html.py
"""
import html
import re
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]

# (section anchor, kind, text): kind = approve (engineer decision) | check (verify the fact) | doubt (my uncertainty) | open (not done yet)
REVIEW=[
    ('r5','doubt','Р5: частота As-Is «1–2 раза в сутки» и нормы времени шагов — экспертная оценка владельца процесса, так и помечено. Для факта нужен хронометраж, выгрузка из журналов или опрос коллег.'),
    ('r4','open','Р4: лимиты такта (5 LLM, 5 GAP, 6 PROSPER, 3 инцидента) и суточный бюджет (20 LLM, 30 GAP) — обсуждаем отдельно.'),
    ('r4','open','Р4: DeepSeek и GLM через OpenRouter отвечают «Access denied by security policy» — ограничение сети или настроек аккаунта OpenRouter.'),
    ('r4','check','Р4: скрининг одиночных скважин gpt-4.1 в настоящем прогоне не выбирала (одной скважины мало) — ветка проверена только на заглушках.'),
    ('r3','doubt','Р3 / критерий 3.1: агент по расписанию запускается командой. Для надёжных 2 баллов лучше задача в Планировщике Windows — это настройка вашей системы, решение за вами.'),
]
LABEL={'approve':'Утвердить','check':'Проверить','doubt':'Сомнение','open':'Не сделано'}


def inline(text):
    text=html.escape(text,quote=False)
    text=re.sub(r'`([^`]+)`',r'<code>\1</code>',text)
    text=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',text)
    return text


def convert(markdown):
    lines=markdown.split('\n');out=[];toc=[];i=0
    def anchor(title):
        match=re.match(r'Р(\d)',title)
        return 'r'+match.group(1) if match else 'log' if 'Improvement' in title else re.sub(r'\W+','-',title.lower()).strip('-')[:40]
    while i<len(lines):
        line=lines[i]
        if line.startswith('# '):i+=1;continue
        if line.startswith('## '):
            title=line[3:].strip();aid=anchor(title);toc.append((aid,title))
            out.append(f'<h2 id="{aid}">{inline(title)}</h2>');i+=1;continue
        if line.startswith('### '):out.append(f'<h3>{inline(line[4:].strip())}</h3>');i+=1;continue
        if line.strip()=='---':i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].startswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')]);i+=1
            head,body=rows[0],[r for r in rows[1:] if not all(set(c)<=set('-: ') for c in r)]
            table='<div class="table"><table><thead><tr>'+''.join(f'<th>{inline(c)}</th>' for c in head)+'</tr></thead><tbody>'
            table+=''.join('<tr>'+''.join(f'<td>{inline(c)}</td>' for c in r)+'</tr>' for r in body)+'</tbody></table></div>'
            out.append(table);continue
        if line.startswith('- '):
            items=[]
            while i<len(lines) and lines[i].startswith('- '):items.append(lines[i][2:]);i+=1
            out.append('<ul>'+''.join(f'<li>{inline(t)}</li>' for t in items)+'</ul>');continue
        if re.match(r'\d+\. ',line):
            items=[]
            while i<len(lines) and re.match(r'\d+\. ',lines[i]):items.append(re.sub(r'^\d+\. ','',lines[i]));i+=1
            out.append('<ol>'+''.join(f'<li>{inline(t)}</li>' for t in items)+'</ol>');continue
        if line.strip():
            para=[line.strip()];i+=1
            while i<len(lines) and lines[i].strip() and not re.match(r'(#|\||- |\d+\. |---)',lines[i]):para.append(lines[i].strip());i+=1
            out.append(f'<p>{inline(" ".join(para))}</p>');continue
        i+=1
    return '\n'.join(out),toc


STYLE='''
:root{--bg:#f4f6f4;--surface:#ffffff;--ink:#1c2420;--muted:#5c6a63;--line:#d6ddd8;--accent:#9a5410;--accent-soft:#f6ead9;
--approve:#1f5f8b;--approve-soft:#e3eef6;--check:#4d6b2c;--check-soft:#e8f0de;--doubt:#a3331f;--doubt-soft:#f8e4df;--open:#6b5a12;--open-soft:#f3edd2;--code:#eef1ee}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#121614;--surface:#1a201d;--ink:#e3e8e4;--muted:#9aa8a0;--line:#2e3833;--accent:#e2a562;--accent-soft:#33261a;
--approve:#8cc2ea;--approve-soft:#1b2a36;--check:#b3d38c;--check-soft:#202b18;--doubt:#f0a08e;--doubt-soft:#3a1f19;--open:#e3cf7a;--open-soft:#302a12;--code:#232b27}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#121614;--surface:#1a201d;--ink:#e3e8e4;--muted:#9aa8a0;--line:#2e3833;--accent:#e2a562;--accent-soft:#33261a;
--approve:#8cc2ea;--approve-soft:#1b2a36;--check:#b3d38c;--check-soft:#202b18;--doubt:#f0a08e;--doubt-soft:#3a1f19;--open:#e3cf7a;--open-soft:#302a12;--code:#232b27}
body{background:var(--bg);color:var(--ink);font:15px/1.6 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding-inline:20px;padding-block:28px 64px;display:grid;grid-template-columns:230px minmax(0,1fr);gap:40px}
nav{position:sticky;top:calc(env(safe-area-inset-top,0px) + 20px);align-self:start;font-size:13.5px}
nav .kicker{font:600 11px/1 "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:12px}
nav a{display:block;color:var(--ink);text-decoration:none;padding:5px 0 5px 12px;border-left:2px solid var(--line)}
nav a:hover,nav a:focus-visible{border-left-color:var(--accent);color:var(--accent);outline:none}
main{min-width:0}
header h1{font:600 clamp(26px,4vw,36px)/1.15 "IBM Plex Sans Condensed","IBM Plex Sans",sans-serif;margin:0 0 6px;text-wrap:balance}
header .meta{color:var(--muted);font-size:14px;max-width:70ch}
.meta code,p code,td code,li code{font:13px "IBM Plex Mono",ui-monospace,monospace;background:var(--code);padding:1px 5px;border-radius:3px}
h2{font:600 22px/1.25 "IBM Plex Sans Condensed","IBM Plex Sans",sans-serif;margin:48px 0 12px;padding-top:12px;border-top:1px solid var(--line);text-wrap:balance;scroll-margin-top:16px}
h3{font:600 16px/1.3 "IBM Plex Sans",sans-serif;margin:28px 0 8px;color:var(--ink)}
p,li{max-width:72ch}
.table{overflow-x:auto;margin:12px 0 18px;border:1px solid var(--line);border-radius:6px;background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:13.5px;font-variant-numeric:tabular-nums}
th,td{text-align:left;vertical-align:top;padding:8px 10px;border-bottom:1px solid var(--line)}
th{font-weight:600;background:var(--code);white-space:nowrap}
tr:last-child td{border-bottom:none}
.review{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:18px 20px;margin:22px 0 8px}
.review h2{border:0;margin:0 0 4px;padding:0;font-size:19px}
.review .hint{color:var(--muted);font-size:13.5px;margin:0 0 12px}
.review ol{list-style:none;padding:0;margin:0;display:grid;gap:8px}
.review li{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:baseline;max-width:none;padding:8px 10px;border-radius:6px}
.tag{font:600 11px/1 "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;padding:5px 7px;border-radius:4px;white-space:nowrap}
.approve{background:var(--approve-soft)}.approve .tag{color:var(--approve);border:1px solid var(--approve)}
.check{background:var(--check-soft)}.check .tag{color:var(--check);border:1px solid var(--check)}
.doubt{background:var(--doubt-soft)}.doubt .tag{color:var(--doubt);border:1px solid var(--doubt)}
.open{background:var(--open-soft)}.open .tag{color:var(--open);border:1px solid var(--open)}
.review li a{font-size:12.5px;color:var(--accent);white-space:nowrap}
.flags{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px}
.flag{font-size:12.5px;padding:4px 8px;border-radius:4px;border:1px solid var(--line);background:var(--surface);cursor:pointer;color:var(--ink)}
.flag:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.flag[aria-pressed="true"]{border-color:var(--accent);color:var(--accent)}
@media (max-width:860px){.wrap{grid-template-columns:1fr;gap:18px}nav{position:static;display:flex;flex-wrap:wrap;gap:4px 14px}nav .kicker{width:100%}nav a{border-left:0;padding:2px 0}
.review li{grid-template-columns:1fr}}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
'''


def build():
    source=(REPO/'course/passport.md').read_text(encoding='utf-8')
    title=source.split('\n',1)[0].lstrip('# ').strip()
    meta=source.split('\n')[2:4]
    body,toc=convert(source)
    items=''.join(f'<li class="{kind}" data-kind="{kind}"><span class="tag">{LABEL[kind]}</span><span>{html.escape(text)}</span><a href="#{aid}">к разделу</a></li>' for aid,kind,text in REVIEW)
    counts={k:sum(1 for _,kind,_ in REVIEW if kind==k) for k in LABEL}
    flags=''.join(f'<button class="flag" type="button" data-kind="{k}" aria-pressed="false">{LABEL[k]} · {counts[k]}</button>' for k in LABEL)
    nav=''.join(f'<a href="#{aid}">{html.escape(t)}</a>' for aid,t in toc)
    page=f'''<title>Паспорт агента мониторинга добычи</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Condensed:wght@600&family=IBM+Plex+Sans:wght@400;600&display=swap">
<style>{STYLE}</style>
<div class="wrap">
<nav aria-label="Разделы паспорта"><div class="kicker">Разделы</div><a href="#review">Проверить и утвердить</a>{nav}</nav>
<main>
<header><h1>{html.escape(title)}</h1><div class="meta">{"<br>".join(inline(m) for m in meta if m.strip())}</div></header>
<section class="review" id="review"><h2>Что проверить и утвердить</h2>
<p class="hint">Пункты, где нужно ваше решение, факт процесса или где я не уверен. Фильтр — по типу.</p>
<div class="flags">{flags}</div><ol>{items}</ol></section>
{body}
</main></div>
<script>
(function(){{var buttons=document.querySelectorAll('.flag');var rows=document.querySelectorAll('.review li');var active=null;
buttons.forEach(function(b){{b.addEventListener('click',function(){{active=active===b.dataset.kind?null:b.dataset.kind;
buttons.forEach(function(x){{x.setAttribute('aria-pressed',String(x.dataset.kind===active));}});
rows.forEach(function(r){{r.hidden=!!active&&r.dataset.kind!==active;}});}});}});}})();
</script>
'''
    (REPO/'course/passport.html').write_text(page,encoding='utf-8')
    return REPO/'course/passport.html'


if __name__=='__main__':
    print(build())
