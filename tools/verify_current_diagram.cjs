const {chromium}=require('C:/Users/User1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try {
  const page=await browser.newPage();
  await page.goto('file:///'+path.resolve('system-dataflow-20260921.html').replaceAll('\\','/'));
  for(const [width,height] of [[1440,900],[1600,1000],[1920,1080],[2048,1320]]){
   await page.setViewportSize({width,height});
   await page.waitForTimeout(300);
   const bounds=await page.evaluate(()=>({width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight}));
   console.log(JSON.stringify(bounds));
   if(bounds.scrollWidth>width || bounds.scrollHeight>height)throw Error('Diagram overflow');
  }
  await page.screenshot({path:'data/diagram-20260921-large.png'});
  await page.locator('#btn-theme').click();
  await page.setViewportSize({width:1440,height:900});
  await page.screenshot({path:'data/diagram-20260921-small-other-theme.png'});
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
