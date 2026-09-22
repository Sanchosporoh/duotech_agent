const {chromium}=require('C:/Users/User1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8503/');
  try {await page.getByRole('heading',{name:'Мониторинг по входным измерениям'}).waitFor({timeout:15000});}
  catch(error){await page.screenshot({path:'data/dashboard-status-20260921-error.png',fullPage:true});console.error((await page.locator('body').innerText()).slice(0,6000));throw error;}
  await page.getByText('Текущий час: 00:00',{exact:true}).waitFor();
  await page.waitForTimeout(1500);
  const exception=await page.locator('[data-testid="stException"]').allTextContents();
  if(exception.length || errors.length)throw new Error(JSON.stringify({exception,errors}));
  await page.screenshot({path:'data/dashboard-status-20260921.png',fullPage:true});
  await page.locator('[data-testid="stVegaLiteChart"]').nth(2).screenshot({path:'data/dashboard-tiles-20260921.png'});
  console.log(JSON.stringify({url:page.url(),hour:'00:00',streamlitExceptions:exception.length,pageErrors:errors.length, screenshot:'data/dashboard-status-20260921.png'}));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
