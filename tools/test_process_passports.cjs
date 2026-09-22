const {chromium}=require('C:/Users/User1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('file:///'+path.resolve('process-archify.html').replaceAll('\\','/'));
  for(const id of ['diagnosis','gap','approval','wait']){
   await page.locator(`#node-${id}`).focus();await page.keyboard.press('Enter');
   await page.waitForFunction(value=>document.getElementById('focus-id').textContent.trim()===value,id);
   const section=page.locator('#engineering-passport');
   if(!await section.isVisible())throw Error(`Passport hidden: ${id}`);
   if(await section.locator('dt').count()!==7)throw Error(`Incomplete passport: ${id}`);
   console.log('Passport OK:',id);
   await page.keyboard.press('Escape');
  }
  if(errors.length)throw Error(errors.join('\n'));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
