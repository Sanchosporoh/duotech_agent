"""Build course/passport.html from course/passport.md (readable version for the reviewer).

Run: python tools/build_passport_html.py
"""
import html
import re
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]


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
        if line.startswith('```'):
            block=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):block.append(html.escape(lines[i]));i+=1
            out.append('<pre>'+'\n'.join(block)+'</pre>');i+=1;continue
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
            while i<len(lines) and lines[i].strip() and not re.match(r'(#|\||- |\d+\. |---|```)',lines[i]):para.append(lines[i].strip());i+=1
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
@media (max-width:860px){.wrap{grid-template-columns:1fr;gap:18px}nav{position:static;display:flex;flex-wrap:wrap;gap:4px 14px}nav .kicker{width:100%}nav a{border-left:0;padding:2px 0}}
pre{background:var(--code);border:1px solid var(--line);border-radius:6px;padding:12px 14px;overflow-x:auto;font:12.5px/1.5 "IBM Plex Mono",ui-monospace,monospace;margin:12px 0}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
'''


def build():
    source=(REPO/'course/passport.md').read_text(encoding='utf-8')
    title=source.split('\n',1)[0].lstrip('# ').strip()
    meta=source.split('\n')[2:4]
    body,toc=convert(source)
    nav=''.join(f'<a href="#{aid}">{html.escape(t)}</a>' for aid,t in toc)
    page=f'''<title>Паспорт агента мониторинга добычи</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Condensed:wght@600&family=IBM+Plex+Sans:wght@400;600&display=swap">
<style>{STYLE}</style>
<div class="wrap">
<nav aria-label="Разделы паспорта"><div class="kicker">Разделы</div>{nav}</nav>
<main>
<header><h1>{html.escape(title)}</h1><div class="meta">{"<br>".join(inline(m) for m in meta if m.strip())}</div></header>
{body}
</main></div>
'''
    (REPO/'course/passport.html').write_text(page,encoding='utf-8')
    return REPO/'course/passport.html'


if __name__=='__main__':
    print(build())
