// Project-specific extension; preserves the generated Archify diagram topology.
import {readFileSync,writeFileSync} from 'node:fs';
const base=readFileSync('process-archify.html','utf8');
const data=JSON.parse(readFileSync('process-passports.json','utf8'));
const specification=JSON.parse(readFileSync('process.workflow.json','utf8'));
for(const node of specification.nodes){if(!data[node.id])throw Error(`Missing passport: ${node.id}`);}
const marker='<!-- PROJECT_ENGINEERING_PASSPORT -->';
const clean=base.includes(marker)?base.slice(0,base.indexOf(marker))+'</body></html>':base;
const extension=`${marker}
<style>
#engineering-passport{white-space:normal;line-height:1.5;margin-top:12px;border-top:1px solid currentColor;padding-top:10px}
#engineering-passport dl{margin:0}#engineering-passport dt{font-weight:600;margin-top:9px}#engineering-passport dd{margin:3px 0 0;overflow-wrap:anywhere}
#engineering-passport summary{cursor:pointer;font-weight:600}
</style>
<script>
(()=>{
 const explanations=${JSON.stringify(data).replaceAll('<','\\u003c')};
 const id=document.getElementById('focus-id');
 const detail=document.getElementById('focus-detail');
 if(!id||!detail)throw Error('Semantic Passport anchors missing');
 const section=document.createElement('details');
 section.id='engineering-passport';section.open=true;
 const summary=document.createElement('summary');summary.textContent='Описание инженерного этапа';
 const content=document.createElement('dl');section.append(summary,content);
 detail.after(section);
 function update(){
   const item=explanations[id.textContent.trim()];content.replaceChildren();section.hidden=!item;
   if(!item)return;
   for(const [label,text] of Object.entries(item)){
     const term=document.createElement('dt');term.textContent=label;
     const value=document.createElement('dd');value.textContent=text;
     content.append(term,value);
   }
 }
 new MutationObserver(update).observe(id,{childList:true,subtree:true,characterData:true});update();
})();
</script>
`;
writeFileSync('process-archify.html',clean.replace('</body>',extension+'</body>'),'utf8');
console.log(`Engineering passports added: ${Object.keys(data).length}`);
